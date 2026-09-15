/* Moved verbatim from App.tsx; only the imports are new. */
import { useRef, useState } from "react";
import { Alert, Image, Modal, Pressable, SafeAreaView, ScrollView, Text, View } from "react-native";
import { CameraView, useCameraPermissions, type CameraCapturedPicture } from "expo-camera";
import { randomUUID } from "expo-crypto";
import { Directory, File, Paths } from "expo-file-system";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";
import type { ApiClient } from "../api";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";
import { useSession } from "../session";
import type { RootParamList } from "../navigation/routes";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { analyzeFrame, decodeBase64, decodeJpeg, qualityMessages } from "../quality";
import { ScaleMark } from "../ScaleMark";
import { queueDraft } from "../storage";
import { syncDraft } from "../sync";
import { Choice, ChoiceRow, Header, Loading, Primary } from "../ui/primitives";
import { styles } from "../theme";
import type { AccountScope, CapturedPanel, Draft, FrameQualityReport, ScaleReference, ScanResult } from "../types";

const CATEGORIES=["FOOD","COSMETIC","GENERIC","CEMENT","FERTILIZER","FARM_PRODUCE","TOBACCO","DRUG_FORMULATION","MEDICAL_DEVICE"];
const PANELS: CapturedPanel["panel"][]=["FRONT","BACK","SIDE_1","SIDE_2"];

function CaptureForm({scope,client,investigationId,cancel,complete}:{scope:AccountScope;client:ApiClient;investigationId:string;cancel:()=>void;complete:(result:ScanResult)=>void}) {
  const [stage,setStage]=useState<"details"|"camera"|"review"|"upload">("details");const [category,setCategory]=useState("FOOD");const [buyerType,setBuyerType]=useState<Draft["buyerType"]>("RETAIL");const [shape,setShape]=useState<Draft["packageShape"]>("RECTANGULAR");const [panels,setPanels]=useState<CapturedPanel[]>([]);const [current,setCurrent]=useState<CapturedPanel["panel"]>("FRONT");const [coverage,setCoverage]=useState(false);const [error,setError]=useState("");
  const [scaleRef,setScaleRef]=useState<ScaleReference|undefined>(undefined);const [markScale,setMarkScale]=useState(false);
  const [permission,requestPermission]=useCameraPermissions();const camera=useRef<CameraView>(null);const [taking,setTaking]=useState(false);
  function start(panel:CapturedPanel["panel"]){setCurrent(panel);setStage("camera");if(!permission?.granted)requestPermission();}
  async function keepPicture(picture:CameraCapturedPicture,source:CapturedPanel["source"]){setTaking(true);try{const longest=Math.max(picture.width,picture.height);const actions=longest>3200?[{resize:picture.width>=picture.height?{width:3200}:{height:3200}}]:[];const processed=await manipulateAsync(picture.uri,actions,{compress:.9,format:SaveFormat.JPEG});const directory=new Directory(Paths.document,"evidence");if(!directory.exists)directory.create({intermediates:true});const target=new File(directory,`${randomUUID()}-${current}.jpg`);await new File(processed.uri).copy(target,{overwrite:true});
    const quality=await measure(target.uri,source);
    const proceed=(report:FrameQualityReport|undefined)=>{setPanels(previous=>[...previous.filter(item=>item.panel!==current),{panel:current,uri:target.uri,source,quality:report}]);if(source==="GALLERY")setCoverage(false);setStage("review");};
    if(quality&&quality.warnings.length){
      const messages=qualityMessages(quality.warnings).join("\n");
      if(source==="CAMERA"){
        Alert.alert("Check this photo",`${messages}\n\nRetake for stronger evidence.`,[
          {text:"Keep anyway",onPress:()=>proceed(quality)},{text:"Retake",style:"cancel",onPress:()=>setStage("camera")}]);
        return;
      }
      Alert.alert("Imported photo quality",`${messages}\nGallery evidence cannot establish coverage. Retake with the in-app camera before asserting coverage.`);
      proceed(quality);
      return;
    }
    proceed(quality);
  }catch(cause){setError(cause instanceof Error?cause.message:"Could not save photo");}finally{setTaking(false);}}
  async function measure(uri:string,source:CapturedPanel["source"]):Promise<FrameQualityReport|undefined>{try{const probe=await manipulateAsync(uri,[{resize:{width:256}}],{compress:.5,format:SaveFormat.JPEG});const encoded=await new File(probe.uri).base64();await new File(probe.uri).delete();return analyzeFrame(decodeJpeg(decodeBase64(encoded)),source);}catch{return undefined;}}
  async function take(){if(!camera.current||taking)return;const picture=await camera.current.takePictureAsync({quality:.95,skipProcessing:false});await keepPicture(picture,"CAMERA");}
  async function pick(){const result=await ImagePicker.launchImageLibraryAsync({mediaTypes:["images"],quality:1});if(!result.canceled){const asset=result.assets[0];await keepPicture({uri:asset.uri,width:asset.width,height:asset.height,format:"jpg"},"GALLERY");}}
  async function submit(){const hasRequired=panels.some(x=>x.panel==="FRONT")&&panels.some(x=>x.panel==="BACK");if(!hasRequired){setError("Front and back photographs are required before submission.");return;}const draft:Draft={clientUuid:randomUUID(),capturedAt:new Date().toISOString().slice(0,10),category,buyerType,packageShape:shape,coverageAsserted:coverage,panels,mode:"PHYSICAL_PACKAGE",scaleReference:scaleRef&&scaleRef.type==="ISO_ID1_CARD"?scaleRef:undefined};setStage("upload");setError("");try{await queueDraft(draft,scope,investigationId);}catch(cause){setStage("review");setError(cause instanceof Error?`Could not save this inspection: ${cause.message}`:"Could not save this inspection for offline use.");return;}try{complete(await syncDraft(client,scope,draft,investigationId));}catch{Alert.alert("Saved for retry","The evidence is safe on this phone. It will sync automatically when this account can reach the local server.");cancel();}}
  if(stage==="upload")return <Loading label="Securing evidence and running compliance checks…"/>;
  if(stage==="camera")return <View style={styles.cameraPage}>{permission?.granted?<CameraView ref={camera} style={styles.flex} facing="back" mode="picture"><View style={styles.captureOverlay}><View><Text style={styles.cameraPanel}>{current.replaceAll("_"," ")} PANEL</Text><Text style={styles.cameraInstruction}>Keep the label square, fill the frame, avoid glare.</Text></View><View style={styles.guideFrame}/><View style={styles.captureActions}><Pressable onPress={()=>setStage("review")}><Text style={styles.cameraLink}>Cancel</Text></Pressable><Pressable style={styles.shutter} onPress={take} disabled={taking}><View style={styles.shutterInner}/></Pressable><Pressable onPress={pick}><Text style={styles.cameraLink}>Gallery</Text></Pressable></View></View></CameraView>:<View style={styles.center}><Text style={styles.h2}>Camera permission is required</Text><Primary label="Allow camera" onPress={requestPermission}/><Pressable onPress={()=>setStage("review")}><Text style={styles.link}>Cancel</Text></Pressable></View>}</View>;
  if(stage==="details")return <View style={styles.flex}><Header title="New inspection" action="Cancel" onAction={cancel}/><ScrollView contentContainerStyle={styles.page}><Text style={styles.eyebrow}>STEP 1 OF 3</Text><Text style={styles.h1}>Package context</Text><Text style={styles.label}>BUYER TYPE</Text><ChoiceRow values={["RETAIL","INDUSTRIAL","INSTITUTIONAL"]} selected={buyerType} select={value=>setBuyerType(value as Draft["buyerType"])}/>{buyerType!=="RETAIL"&&<View style={styles.warning}><Text style={styles.warningTitle}>This will normally be out of scope</Text><Text style={styles.warningText}>Industrial and institutional packages are stopped at the applicability gate under Rule 3. Select Retail when this package is sold to an individual consumer.</Text></View>}<Text style={styles.label}>COMMODITY CATEGORY</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.choiceScroll}>{CATEGORIES.map(value=><Choice key={value} value={value} selected={category===value} onPress={()=>setCategory(value)}/>)}</ScrollView><Text style={styles.label}>PACKAGE SHAPE</Text><ChoiceRow values={["RECTANGULAR","CYLINDRICAL","IRREGULAR"]} selected={shape} select={value=>setShape(value as Draft["packageShape"])}/><Primary label="Start photographs" onPress={()=>start("FRONT")}/></ScrollView></View>;
  const hasFront=panels.some(x=>x.panel==="FRONT"),hasBack=panels.some(x=>x.panel==="BACK");const canAssert=hasFront&&hasBack&&panels.every(item=>item.source==="CAMERA");
  return <View style={styles.flex}><Header title="Photographs" action="Cancel" onAction={cancel}/><ScrollView contentContainerStyle={styles.page}><Text style={styles.eyebrow}>STEP 2 OF 3</Text><Text style={styles.h1}>Package surfaces</Text><Text style={styles.body}>Front and back are required. Add side panels when declarations continue around the package.</Text><View style={styles.panelGrid}>{PANELS.map(panel=>{const photo=panels.find(item=>item.panel===panel);return <Pressable key={panel} style={styles.panelCard} onPress={()=>start(panel)}>{photo?<Image source={{uri:photo.uri}} style={styles.thumbnail}/>:<View style={styles.panelEmpty}><Text style={styles.plus}>＋</Text></View>}<Text style={styles.panelLabel}>{panel.replaceAll("_"," ")}</Text><Text style={styles.muted}>{photo?`${photo.source==="GALLERY"?"Gallery evidence":"Camera evidence"} · tap to retake`:panel==="FRONT"||panel==="BACK"?"Required":"Optional"}</Text></Pressable>;})}</View><Pressable style={[styles.checkRow,!canAssert&&styles.disabled]} disabled={!canAssert} onPress={()=>setCoverage(!coverage)}><View style={[styles.checkbox,coverage&&styles.checkboxOn]}>{coverage&&<Text style={styles.checkmark}>✓</Text>}</View><View style={styles.flex}><Text style={styles.checkTitle}>I photographed every declaration-bearing surface</Text><Text style={styles.muted}>This allows the engine to distinguish proven absence from missing evidence.</Text></View></Pressable><Pressable style={[styles.checkRow,!hasFront&&styles.disabled]} disabled={!hasFront} onPress={()=>setMarkScale(true)}><View style={[styles.checkbox,!!scaleRef&&scaleRef.type==="ISO_ID1_CARD"&&styles.checkboxOn]}>{scaleRef&&scaleRef.type==="ISO_ID1_CARD"&&<Text style={styles.checkmark}>✓</Text>}</View><View style={styles.flex}><Text style={styles.checkTitle}>Mark a scale reference (optional)</Text><Text style={styles.muted}>{scaleRef&&scaleRef.type==="ISO_ID1_CARD"?"Card and panel corner marks will travel with this inspection.":"Lay an ID-1 card on the front face and mark its corners so millimetre checks can run."}</Text></View></Pressable>{hasFront&&hasBack&&!canAssert&&<View style={styles.warning}><Text style={styles.warningTitle}>Gallery evidence cannot establish coverage</Text><Text style={styles.warningText}>Retake imported panels with the in-app camera before asserting that every surface was photographed.</Text></View>}{!coverage&&hasFront&&hasBack&&canAssert&&<View style={styles.info}><Text style={styles.infoText}>You can submit without this assertion, but missing declarations will be reported as “cannot determine,” not violations.</Text></View>}{error&&<Text style={styles.error}>{error}</Text>}<Primary label="Submit and analyse" onPress={submit} disabled={!hasFront||!hasBack}/></ScrollView><Modal visible={markScale} animationType="slide" onRequestClose={()=>setMarkScale(false)}><SafeAreaView style={styles.safe}>{panels.some(x=>x.panel==="FRONT")&&<ScaleMark imageUri={panels.find(x=>x.panel==="FRONT")!.uri} onDone={(reference)=>{setScaleRef(reference.type==="ISO_ID1_CARD"?reference:undefined);setMarkScale(false);}} onCancel={()=>setMarkScale(false)}/>}</SafeAreaView></Modal></View>;
}


/** Route adapter. The capture wizard above is the original code, moved verbatim; this
 *  supplies it with the session and the folder the scan is being filed into. */
export function CaptureScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootParamList>>();
  const route = useRoute<RouteProp<RootParamList, "Capture">>();
  const {client, scope} = useSession();
  return <CaptureForm
    scope={scope} client={client}
    investigationId={route.params.investigationId}
    cancel={() => navigation.goBack()}
    complete={(result) => navigation.replace("ScanReport",
      {clientUuid: result.client_uuid, scanId: result.scan_id})} />;
}
