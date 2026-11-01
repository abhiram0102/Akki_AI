declare module "react-flow" {
  import * as React from "react";

  export const ReactFlow: React.ComponentType<any>;
  export const ReactFlowProvider: React.ComponentType<{ children: React.ReactNode }>;
  export function useReactFlow(): any;
}