declare module 'expo-image-picker' {
  export type PermissionStatus = 'granted' | 'denied' | 'undetermined';
  export type ImagePickerAsset = {
    uri: string;
    fileName?: string | null;
    fileSize?: number;
    mimeType?: string;
    type?: string;
  };
  export type ImagePickerResult =
    | { canceled: true; assets?: null }
    | { canceled: false; assets: ImagePickerAsset[] };
  export enum MediaTypeOptions {
    Images = 'Images',
  }
  export function requestMediaLibraryPermissionsAsync(): Promise<{ status: PermissionStatus; granted: boolean }>;
  export function launchImageLibraryAsync(options?: {
    mediaTypes?: MediaTypeOptions;
    allowsEditing?: boolean;
    quality?: number;
  }): Promise<ImagePickerResult>;
}
