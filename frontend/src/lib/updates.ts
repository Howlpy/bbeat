import { Capacitor, registerPlugin } from '@capacitor/core';

interface BbeatUpdaterPlugin {
  getCurrentVersion(): Promise<{ versionName: string; versionCode: number }>;
  downloadAndInstall(options: { url: string }): Promise<{ installerOpened: boolean }>;
}

export interface UpdateInfo {
  currentVersion: string;
  latestVersion: string;
  updateAvailable: boolean;
  downloadUrl: string;
  releaseUrl: string;
}

const NativeUpdater = registerPlugin<BbeatUpdaterPlugin>('BbeatUpdater');

function versionParts(version: string): number[] {
  return version.replace(/^v/i, '').split('.').map((part) => Number.parseInt(part, 10) || 0);
}

function isNewer(candidate: string, current: string): boolean {
  const left = versionParts(candidate);
  const right = versionParts(current);
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i++) {
    const difference = (left[i] ?? 0) - (right[i] ?? 0);
    if (difference !== 0) return difference > 0;
  }
  return false;
}

export const updates = {
  available: Capacitor.isNativePlatform(),

  async check(): Promise<UpdateInfo> {
    const current = await NativeUpdater.getCurrentVersion();
    const response = await fetch('https://api.github.com/repos/Howlpy/bbeat/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' },
      cache: 'no-store'
    });
    if (!response.ok) throw new Error(`GitHub respondió con HTTP ${response.status}`);

    const release = (await response.json()) as {
      tag_name?: string;
      html_url?: string;
      assets?: { name?: string; browser_download_url?: string; content_type?: string }[];
    };
    const apk = release.assets?.find(
      (asset) => asset.name?.toLowerCase().endsWith('.apk') ||
        asset.content_type === 'application/vnd.android.package-archive'
    );
    if (!release.tag_name || !release.html_url || !apk?.browser_download_url) {
      throw new Error('La última release no contiene un APK instalable');
    }

    return {
      currentVersion: current.versionName,
      latestVersion: release.tag_name.replace(/^v/i, ''),
      updateAvailable: isNewer(release.tag_name, current.versionName),
      downloadUrl: apk.browser_download_url,
      releaseUrl: release.html_url
    };
  },

  install(downloadUrl: string) {
    return NativeUpdater.downloadAndInstall({ url: downloadUrl });
  }
};
