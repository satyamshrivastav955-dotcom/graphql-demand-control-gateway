/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Sentinel gateway; empty/unset means same origin. */
  readonly VITE_API_URL?: string;
}
