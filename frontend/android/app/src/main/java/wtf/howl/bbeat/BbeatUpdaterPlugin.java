package wtf.howl.bbeat;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.activity.result.ActivityResult;
import androidx.core.content.FileProvider;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "BbeatUpdater")
public class BbeatUpdaterPlugin extends Plugin {
    private static final long MAX_APK_BYTES = 250L * 1024L * 1024L;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void getCurrentVersion(PluginCall call) {
        JSObject result = new JSObject();
        PackageInfo packageInfo = packageInfo();
        result.put("versionName", packageInfo == null || packageInfo.versionName == null ? "0.0.0" : packageInfo.versionName);
        result.put("versionCode", packageInfo == null ? 0 : versionCode(packageInfo));
        call.resolve(result);
    }

    @PluginMethod
    public void downloadAndInstall(PluginCall call) {
        String url = call.getString("url", "");
        if (!isOfficialReleaseUrl(url)) {
            call.reject("La actualización no procede del repositorio oficial de BBeat");
            return;
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !getContext().getPackageManager().canRequestPackageInstalls()) {
            Intent permissionIntent = new Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + getContext().getPackageName())
            );
            startActivityForResult(call, permissionIntent, "installPermissionResult");
            return;
        }

        beginDownload(call);
    }

    @ActivityCallback
    private void installPermissionResult(PluginCall call, ActivityResult ignored) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !getContext().getPackageManager().canRequestPackageInstalls()) {
            call.reject("Debes permitir que BBeat instale aplicaciones para continuar");
            return;
        }
        beginDownload(call);
    }

    private void beginDownload(PluginCall call) {
        String url = call.getString("url", "");
        executor.execute(() -> {
            try {
                File apk = downloadApk(url);
                getActivity().runOnUiThread(() -> openInstaller(call, apk));
            } catch (Exception error) {
                call.reject("No se pudo descargar la actualización: " + error.getMessage(), error);
            }
        });
    }

    private File downloadApk(String source) throws IOException {
        File updateDir = new File(getContext().getCacheDir(), "updates");
        if (!updateDir.exists() && !updateDir.mkdirs()) {
            throw new IOException("no se pudo crear el directorio temporal");
        }

        File destination = new File(updateDir, "bbeat-update.apk");
        if (destination.exists() && !destination.delete()) {
            throw new IOException("no se pudo reemplazar la descarga anterior");
        }

        HttpURLConnection connection = openConnectionFollowingTrustedRedirects(source);
        long declaredSize = connection.getContentLengthLong();
        if (declaredSize > MAX_APK_BYTES) {
            connection.disconnect();
            throw new IOException("el archivo es demasiado grande");
        }

        long total = 0;
        try (
            BufferedInputStream input = new BufferedInputStream(connection.getInputStream());
            BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(destination))
        ) {
            byte[] buffer = new byte[32 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_APK_BYTES) throw new IOException("el archivo es demasiado grande");
                output.write(buffer, 0, read);
            }
        } catch (IOException error) {
            destination.delete();
            throw error;
        } finally {
            connection.disconnect();
        }

        if (total < 4 || !looksLikeZip(destination)) {
            destination.delete();
            throw new IOException("GitHub no devolvió un APK válido");
        }
        return destination;
    }

    private HttpURLConnection openConnectionFollowingTrustedRedirects(String source) throws IOException {
        URL current = new URL(source);
        for (int redirects = 0; redirects <= 5; redirects++) {
            if (!isTrustedDownloadHost(current)) throw new IOException("redirección de descarga no fiable");

            HttpURLConnection connection = (HttpURLConnection) current.openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(60_000);
            connection.setRequestProperty("Accept", "application/vnd.android.package-archive, application/octet-stream");
            connection.setRequestProperty("User-Agent", "BBeat-Android-Updater");

            int status = connection.getResponseCode();
            if (status >= 200 && status < 300) return connection;
            if (status < 300 || status >= 400) {
                connection.disconnect();
                throw new IOException("GitHub respondió con HTTP " + status);
            }

            String location = connection.getHeaderField("Location");
            connection.disconnect();
            if (location == null) throw new IOException("redirección sin destino");
            current = new URL(current, location);
        }
        throw new IOException("demasiadas redirecciones");
    }

    private boolean isOfficialReleaseUrl(String value) {
        try {
            URL url = new URL(value);
            return "https".equalsIgnoreCase(url.getProtocol()) &&
                "github.com".equalsIgnoreCase(url.getHost()) &&
                url.getPath().toLowerCase(Locale.ROOT).startsWith("/howlpy/bbeat/releases/download/") &&
                url.getPath().toLowerCase(Locale.ROOT).endsWith(".apk");
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean isTrustedDownloadHost(URL url) {
        if (!"https".equalsIgnoreCase(url.getProtocol())) return false;
        String host = url.getHost().toLowerCase(Locale.ROOT);
        return host.equals("github.com") || host.endsWith(".githubusercontent.com");
    }

    private boolean looksLikeZip(File file) throws IOException {
        try (FileInputStream input = new FileInputStream(file)) {
            return input.read() == 'P' && input.read() == 'K' && input.read() == 3 && input.read() == 4;
        }
    }

    private PackageInfo packageInfo() {
        try {
            return getContext().getPackageManager().getPackageInfo(getContext().getPackageName(), 0);
        } catch (PackageManager.NameNotFoundException ignored) {
            return null;
        }
    }

    @SuppressWarnings("deprecation")
    private long versionCode(PackageInfo packageInfo) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) return packageInfo.getLongVersionCode();
        return packageInfo.versionCode;
    }

    private void openInstaller(PluginCall call, File apk) {
        try {
            Uri uri = FileProvider.getUriForFile(
                getContext(),
                getContext().getPackageName() + ".fileprovider",
                apk
            );
            Intent intent = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(intent);
            JSObject result = new JSObject();
            result.put("installerOpened", true);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("No se pudo abrir el instalador de Android", error);
        }
    }

    @Override
    protected void handleOnDestroy() {
        executor.shutdownNow();
        super.handleOnDestroy();
    }
}
