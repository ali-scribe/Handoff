/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL of the backend API for production builds (e.g. the FastAPI Cloud
   * origin, "https://your-app.fastapicloud.dev"). Leave unset for local
   * development, where requests stay relative and use the Vite dev proxy.
   */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}