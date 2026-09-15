/* The route table.
 *
 * Screens take ids, never objects. The old navigation kept a whole ScanResult in
 * navigation state, which meant a result could not be restored after a process kill,
 * refreshed, or opened from anywhere but the screen that produced it. */
export type AppRoutes = {
  Investigations: undefined;
  InvestigationEdit: { investigationId?: string };
  Investigation: { investigationId: string };
  Capture: { investigationId: string };
  ListingCapture: { investigationId: string };
  ScanReport: { clientUuid: string; scanId: string | null };
  EvidenceViewer: { clientUuid: string; panel: string };
  Settings: undefined;
};

declare global {
  namespace ReactNavigation {
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface RootParamList extends AppRoutes {}
  }
}

export type RootParamList = AppRoutes;
