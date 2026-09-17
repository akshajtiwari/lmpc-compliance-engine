import { CryptoDigestAlgorithm, digest } from "expo-crypto";
import { Directory, File, Paths } from "expo-file-system";
import type {
  Draft, InvestigationNote, InvestigationStats, Principal, ReportSummary, RuleDetail, ScanResult, ScanSummary, ServerInvestigation, Session,
} from "./types";
import { saveSession } from "./storage";

type AuthBody = { access_token: string; refresh_token: string; user: Principal; server_fingerprint?: string };
type VersionBody = { server_fingerprint: string };
type SessionChanged = (session: Session | null) => void;

export class ConnectionError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ConnectionError";
  }
}

export function isConnectionError(cause: unknown): cause is ConnectionError {
  return cause instanceof ConnectionError;
}

function hostOf(url: string) {
  try { return new URL(url).host; } catch { return "the server"; }
}

async function timedFetch(url: string, options: RequestInit = {}, timeoutMs = 15_000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {...options, signal: controller.signal});
  } catch (cause) {
    if (cause instanceof Error && cause.name === "AbortError") {
      throw new ConnectionError(`${hostOf(url)} did not respond in time.`, {cause});
    }
    if (cause instanceof TypeError) {
      // Name the address. "Could not reach the server" reads as "we are on different
      // networks" and sends the officer off to check the Wi-Fi, when the usual cause is
      // that the QR carried an address — a VPN or container address on the server — that
      // no phone was ever going to reach.
      throw new ConnectionError(`Could not reach ${hostOf(url)} from this phone. Check that address against the ones listed on the server's "Connect a phone" page.`, {cause});
    }
    throw cause;
  } finally {
    clearTimeout(timeout);
  }
}

async function responseError(response: Response) {
  const message = await errorMessage(response);
  if (response.status === 408 || response.status === 429 || response.status >= 500) {
    return new ConnectionError(message);
  }
  return new Error(message);
}

async function errorMessage(response: Response) {
  try { const body = await response.json() as {error?:{message?:string}}; return body.error?.message ?? `Server returned ${response.status}`; }
  catch { return `Server returned ${response.status}`; }
}

export function normalizeServerUrl(value: string) {
  const trimmed = value.trim().replace(/\/$/, "");
  const parsed = new URL(trimmed);
  if (!/^https?:$/.test(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) throw new Error("Enter an HTTP(S) server address without a path");
  return trimmed;
}

export async function verifyServer(serverUrl: string, expectedFingerprint?: string) {
  const response = await timedFetch(`${serverUrl}/api/v1/version`);
  if (!response.ok) throw await responseError(response);
  const body = await response.json() as VersionBody;
  if (!body.server_fingerprint) throw new Error("The server is not running managed local authentication");
  if (expectedFingerprint && body.server_fingerprint !== expectedFingerprint) throw new Error("Server identity does not match the enrollment QR. Do not continue.");
  return body.server_fingerprint;
}

export async function enrollFromUri(uri: string): Promise<Session> {
  const parsed = new URL(uri);
  if (parsed.protocol !== "lmpc:" || parsed.hostname !== "enroll") throw new Error("This is not an LMPC enrollment QR");
  const serverUrl = normalizeServerUrl(parsed.searchParams.get("server") ?? "");
  const fingerprint = parsed.searchParams.get("fingerprint") ?? "";
  const token = parsed.searchParams.get("token") ?? "";
  if (!fingerprint || token.length < 20) throw new Error("The enrollment QR is incomplete");
  await verifyServer(serverUrl, fingerprint);
  const response = await timedFetch(`${serverUrl}/api/v1/auth/enroll`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token,device_name:"LMPC Field device"})});
  if (!response.ok) throw await responseError(response);
  const body = await response.json() as AuthBody;
  if (body.server_fingerprint !== fingerprint) throw new Error("The enrollment response came from a different server");
  return {serverUrl,fingerprint,accessToken:body.access_token,refreshToken:body.refresh_token,user:body.user};
}

export async function passwordLogin(server: string, email: string, password: string): Promise<Session> {
  const serverUrl=normalizeServerUrl(server); const fingerprint=await verifyServer(serverUrl);
  const response=await timedFetch(`${serverUrl}/api/v1/auth/login`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
  if(!response.ok)throw await responseError(response); const body=await response.json() as AuthBody;
  return {serverUrl,fingerprint,accessToken:body.access_token,refreshToken:body.refresh_token,user:body.user};
}

export class ApiClient {
  constructor(private session: Session, private changed: SessionChanged) {}
  async request<T>(path: string, options: RequestInit = {}, retry = true, timeoutMs = 20_000): Promise<T> {
    const headers=new Headers(options.headers); headers.set("Authorization",`Bearer ${this.session.accessToken}`);
    if(options.body && !(options.body instanceof FormData) && !headers.has("Content-Type"))headers.set("Content-Type","application/json");
    let response=await timedFetch(`${this.session.serverUrl}/api/v1${path}`,{...options,headers},timeoutMs);
    if(response.status===401 && retry){await this.refresh();return this.request<T>(path,options,false,timeoutMs);}
    if(!response.ok)throw await responseError(response);
    if(response.status===204)return undefined as T; return response.json() as Promise<T>;
  }
  private async refresh(){
    await verifyServer(this.session.serverUrl,this.session.fingerprint);
    const response=await timedFetch(`${this.session.serverUrl}/api/v1/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:this.session.refreshToken})});
    if(!response.ok){await saveSession(null);this.changed(null);throw new Error("Your device session expired. Ask an administrator for a new enrollment QR.");}
    const body=await response.json() as AuthBody; this.session={...this.session,accessToken:body.access_token,refreshToken:body.refresh_token,user:body.user}; await saveSession(this.session);this.changed(this.session);
  }
  createInvestigation(values:{client_uuid:string;name:string;subject_brand:string|null;investigation_type:string;location_text:string|null}){
    // Idempotent on client_uuid: a folder opened with no signal and retried for an hour
    // comes back as one investigation, not five.
    return this.request<ServerInvestigation>("/investigations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(values)});
  }
  investigations(params:{q?:string;status?:string;sort?:string}={}){
    const query=new URLSearchParams();
    for(const [key,value] of Object.entries(params))if(value)query.set(key,String(value));
    const suffix=query.toString();
    return this.request<{items:ServerInvestigation[];total:number}>(`/investigations${suffix?`?${suffix}`:""}`);
  }
  investigationStats(id:string){return this.request<InvestigationStats>(`/investigations/${id}/stats`);}
  investigationScans(id:string,page=1){return this.request<{items:ScanSummary[];total:number;pages:number}>(`/investigations/${id}/scans?page=${page}&page_size=50`);}
  investigationNotes(id:string){return this.request<{items:InvestigationNote[]}>(`/investigations/${id}/notes`);}
  addInvestigationNote(id:string,body:string){return this.request<InvestigationNote>(`/investigations/${id}/notes`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body})});}
  closeInvestigation(id:string,status:"OPEN"|"CLOSED"){return this.request<ServerInvestigation>(`/investigations/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});}
  async upload(draft: Draft, investigationId: string | null = null): Promise<ScanResult> {
    // Deferred intake (plan §8 item 9): declare the inspection, then upload each
    // panel on its own request so a flaky network resumes instead of restarting.
    const mode=draft.mode??"PHYSICAL_PACKAGE";
    const form=new FormData();
    form.append("client_uuid",draft.clientUuid);form.append("captured_at",draft.capturedAt);form.append("mode",mode);form.append("category",draft.category);form.append("coverage_asserted",String(draft.coverageAsserted));form.append("buyer_type",draft.buyerType);form.append("package_shape",draft.packageShape);form.append("scale_reference",JSON.stringify(draft.scaleReference??{type:"NONE"}));form.append("flags",JSON.stringify({}));
    if(investigationId)form.append("investigation_id",investigationId);
    if(draft.listing)form.append("ecommerce",JSON.stringify({listing_text:draft.listing.text,url:draft.listing.url}));
    for(const item of draft.panels)form.append("panels",item.panel);
    // begin is idempotent: the retry that timed out gets the scan that already exists.
    const begun=await this.request<ScanResult>("/scans/deferred",{method:"POST",body:form},true,45_000);
    if(!begun.evaluations?.length){
      const uploaded=new Set(begun.images?.map(image=>image.panel)??[]);
      for(const item of draft.panels){
        if(uploaded.has(item.panel))continue;
        const file=new File(item.uri);
        const panelForm=new FormData();
        panelForm.append("panel",item.panel);
        panelForm.append("image_sha256",await sha256(file));
        panelForm.append("image_quality",JSON.stringify(item.quality??{source:item.source}));
        // Append the File itself, not React Native's legacy {uri,name,type} shorthand.
        // Expo's WinterCG fetch builds the multipart body in JS and accepts only a
        // string, a Blob, or something with a bytes() method — its own source says
        // "uri is not supported" — so the shorthand threw "Unsupported FormDataPart
        // implementation" and no panel ever reached the server. File carries bytes(),
        // name and type, which is also what the server checks the MIME against.
        panelForm.append("image", file as unknown as Blob);
        await this.request(`/scans/${begun.scan_id}/images`,{method:"POST",body:panelForm},true,45_000);
      }
      await this.request(`/scans/${begun.scan_id}/complete-upload`,{method:"POST"},true,45_000);
      return this.request<ScanResult>(`/scans/${begun.scan_id}/process`,{method:"POST"},true,120_000);
    }
    return begun;
  }
  rule(check: string){return this.request<RuleDetail>(`/rules/${encodeURIComponent(check)}`);}
  scan(id:string){return this.request<ScanResult>(`/scans/${id}`);}
  reports(scanId:string){return this.request<{items:ReportSummary[]}>(`/scans/${scanId}/reports`);}
  async downloadReport(reportId:string,format:"pdf"|"docx"="pdf"){
    // The metadata call reuses the 401-refresh path, so the download below always
    // starts with a valid access token.
    await this.request(`/reports/${reportId}`);
    const url=`${this.session.serverUrl}/api/v1/reports/${reportId}/download?format=${format}`;
    const directory=new Directory(Paths.cache,"reports");
    if(!directory.exists)directory.create({intermediates:true});
    const target=new File(directory,`lmpc-report-${reportId.slice(0,8)}.${format}`);
    const task=File.createDownloadTask(url,target,
      {headers:{Authorization:`Bearer ${this.session.accessToken}`}});
    const file=await task.downloadAsync();
    if(!file)throw new Error("The report download did not complete");
    return file;
  }
  async logout() {
    try {
      await timedFetch(`${this.session.serverUrl}/api/v1/auth/logout`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({refresh_token: this.session.refreshToken}),
      });
    } finally {
      await saveSession(null);
      this.changed(null);
    }
  }
}

// `bytes()`, not `arrayBuffer()`. expo-crypto's digest is typed as taking a BufferSource,
// but the Kotlin bridge cannot convert a bare ArrayBuffer and fails at runtime with
// "Cannot convert '[object ArrayBuffer]' to a Kotlin type. no ArrayBuffer attached" —
// which stopped every panel upload, and so every scan, on a real device. `File.bytes()`
// hands back a Uint8Array, which is what the native side can actually read.
async function sha256(file: File) { const hashed=await digest(CryptoDigestAlgorithm.SHA256,await file.bytes()); return [...new Uint8Array(hashed)].map(byte=>byte.toString(16).padStart(2,"0")).join(""); }
