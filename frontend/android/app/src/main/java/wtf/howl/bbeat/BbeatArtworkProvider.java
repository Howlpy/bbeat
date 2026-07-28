package wtf.howl.bbeat;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Expone las carátulas remotas como content:// locales. Android Auto y AAOS no
 * aceptan URLs http(s) en MediaDescription/MediaMetadata; necesitan una URI
 * local que puedan abrir mediante ContentResolver.
 */
public class BbeatArtworkProvider extends ContentProvider {
    private static final String PREFS = "bbeat_auto_artwork";
    private static final String PATH = "artwork";

    static Uri uriFor(Context context, String remoteUrl) {
        if (remoteUrl == null || remoteUrl.isEmpty()) return null;
        Uri parsed = Uri.parse(remoteUrl);
        String scheme = parsed.getScheme();
        if (!"http".equalsIgnoreCase(scheme) && !"https".equalsIgnoreCase(scheme)) return null;
        String key = sha256(remoteUrl);
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(key, remoteUrl).apply();
        return new Uri.Builder()
            .scheme("content")
            .authority(context.getPackageName() + ".artwork")
            .appendPath(PATH)
            .appendPath(key)
            .build();
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(digest.length * 2);
            for (byte b : digest) out.append(String.format("%02x", b));
            return out.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    @Override public boolean onCreate() { return true; }

    @Nullable
    @Override
    public ParcelFileDescriptor openFile(@NonNull Uri uri, @NonNull String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Proveedor de solo lectura");
        try {
            return openArtwork(uri);
        } catch (IOException error) {
            FileNotFoundException wrapped = new FileNotFoundException(error.getMessage());
            wrapped.initCause(error);
            throw wrapped;
        }
    }

    private ParcelFileDescriptor openArtwork(Uri uri) throws IOException {
        Context context = getContext();
        if (context == null || uri.getPathSegments().size() != 2 ||
            !PATH.equals(uri.getPathSegments().get(0))) {
            throw new IOException("URI de carátula inválida");
        }
        String key = uri.getLastPathSegment();
        if (key == null || !key.matches("[0-9a-f]{64}")) throw new IOException("Clave inválida");
        String remoteUrl = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(key, null);
        if (remoteUrl == null) throw new IOException("Carátula desconocida");

        File dir = new File(context.getCacheDir(), "auto-artwork");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("No se pudo crear caché");
        File cached = new File(dir, key + ".img");
        if (!cached.isFile() || cached.length() == 0) download(remoteUrl, cached);
        return ParcelFileDescriptor.open(cached, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    private static synchronized void download(String remoteUrl, File destination) throws IOException {
        if (destination.isFile() && destination.length() > 0) return;
        File temporary = new File(destination.getParentFile(), destination.getName() + ".tmp");
        HttpURLConnection connection = (HttpURLConnection) new URL(remoteUrl).openConnection();
        connection.setConnectTimeout(8_000);
        connection.setReadTimeout(12_000);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("User-Agent", "BBeat-Android/1");
        try {
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IOException("HTTP " + status);
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[16 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            }
            if (!temporary.renameTo(destination)) throw new IOException("No se pudo guardar carátula");
        } finally {
            connection.disconnect();
            if (temporary.exists() && !destination.exists()) temporary.delete();
        }
    }

    @Nullable @Override public String getType(@NonNull Uri uri) { return "image/*"; }
    @Nullable @Override public Cursor query(@NonNull Uri uri, @Nullable String[] projection,
        @Nullable String selection, @Nullable String[] selectionArgs, @Nullable String sortOrder) { return null; }
    @Nullable @Override public Uri insert(@NonNull Uri uri, @Nullable ContentValues values) { return null; }
    @Override public int delete(@NonNull Uri uri, @Nullable String selection,
        @Nullable String[] selectionArgs) { return 0; }
    @Override public int update(@NonNull Uri uri, @Nullable ContentValues values,
        @Nullable String selection, @Nullable String[] selectionArgs) { return 0; }
}
