/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ADMITLY_RELEASE?: string;
  readonly VITE_ADMITLY_DIST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
