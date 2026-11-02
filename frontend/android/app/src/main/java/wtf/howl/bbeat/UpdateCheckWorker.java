package wtf.howl.bbeat;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/**
 * Comprueba una vez al día (en segundo plano, con la app cerrada) si hay una
 * release nueva en GitHub y avisa con una notificación del sistema.
 */
public class UpdateCheckWorker extends Worker {
    public static final String EXTRA_OPEN = "bbeat_open";
    private static final String WORK_NAME = "bbeat-update-check";
    private static final String CHANNEL_ID = "updates";
    private static final String PREFS = "bbeat_updates";
    private static final String PREF_LAST_NOTIFIED = "last_notified_tag";
    private static final String API_URL = "https://api.github.com/repos/Howlpy/bbeat/releases/latest";
    private static final int NOTIFICATION_ID = 7001;

    public UpdateCheckWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    /** Programa la comprobación diaria. KEEP: no se reinicia el ciclo en cada arranque. */
    public static void schedule(Context context) {
        Constraints constraints = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build();
        PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(UpdateCheckWorker.class, 24, TimeUnit.HOURS)
            .setConstraints(constraints)
            .build();
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request);
    }

    @NonNull
    @Override
    public Result doWork() {
        // Los fallos son silenciosos: se reintenta en el siguiente ciclo.
        try {
            Context context = getApplicationContext();
            String tag = fetchLatestTag();
            if (tag == null) return Result.success();

            String latest = tag.replaceFirst("^[vV]", "");
            String current = installedVersion(context);
            if (current == null || !isNewer(latest, current)) return Result.success();

            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            if (tag.equals(prefs.getString(PREF_LAST_NOTIFIED, null))) return Result.success();

            if (notifyUpdate(context, latest)) {
                prefs.edit().putString(PREF_LAST_NOTIFIED, tag).apply();
            }
            return Result.success();
        } catch (Exception ignored) {
            return Result.success();
        }
    }

    private String fetchLatestTag() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(API_URL).openConnection();
        try {
            connection.setConnectTimeout(10_000);
            connection.setReadTimeout(15_000);
            connection.setRequestProperty("Accept", "application/vnd.github+json");
            connection.setRequestProperty("User-Agent", "BBeat-Android-Updater");
            if (connection.getResponseCode() != 200) return null;
            StringBuilder body = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                char[] buffer = new char[4096];
                int read;
                while ((read = reader.read(buffer)) != -1) {
                    body.append(buffer, 0, read);
                    if (body.length() > 2_000_000) return null;
                }
            }
            String tag = new JSONObject(body.toString()).optString("tag_name", "");
            return tag.isEmpty() ? null : tag;
        } finally {
            connection.disconnect();
        }
    }

    private String installedVersion(Context context) {
        try {
            return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException ignored) {
            return null;
        }
    }

    // Misma comparación que updates.ts (isNewer): partes numéricas separadas por puntos.
    static boolean isNewer(String candidate, String current) {
        int[] left = parts(candidate);
        int[] right = parts(current);
        int length = Math.max(left.length, right.length);
        for (int i = 0; i < length; i++) {
            int diff = (i < left.length ? left[i] : 0) - (i < right.length ? right[i] : 0);
            if (diff != 0) return diff > 0;
        }
        return false;
    }

    private static int[] parts(String version) {
        String[] raw = version.replaceFirst("^[vV]", "").split("\\.");
        int[] out = new int[raw.length];
        for (int i = 0; i < raw.length; i++) {
            String digits = raw[i].replaceAll("^(\\d+).*$", "$1");
            try {
                out[i] = Integer.parseInt(digits);
            } catch (NumberFormatException ignored) {
                out[i] = 0;
            }
        }
        return out;
    }

    /** @return true si la notificación se publicó (hay permiso). */
    private boolean notifyUpdate(Context context, String version) {
        NotificationManagerCompat manager = NotificationManagerCompat.from(context);
        if (!manager.areNotificationsEnabled()) return false;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "Actualizaciones", NotificationManager.IMPORTANCE_DEFAULT);
            manager.createNotificationChannel(channel);
        }

        Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
        if (launch == null) return false;
        launch.putExtra(EXTRA_OPEN, "settings");
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent tap = PendingIntent.getActivity(
            context, 0, launch, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_bbeat)
            .setContentTitle("Nueva versión de bbeat")
            .setContentText("La versión " + version + " está disponible. Toca para actualizar.")
            .setContentIntent(tap)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT);
        try {
            manager.notify(NOTIFICATION_ID, builder.build());
            return true;
        } catch (SecurityException ignored) {
            return false;
        }
    }
}
