package wtf.howl.bbeat;

import android.Manifest;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(BbeatAutoPlugin.class);
        registerPlugin(BbeatUpdaterPlugin.class);
        super.onCreate(savedInstanceState);

        // Aviso diario de nuevas versiones (WorkManager, sin Firebase).
        UpdateCheckWorker.schedule(this);
        askNotificationPermissionOnce();
    }

    // Android 13+: pide POST_NOTIFICATIONS una sola vez (primer arranque).
    private void askNotificationPermissionOnce() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED) return;
        SharedPreferences prefs = getSharedPreferences("bbeat_updates", MODE_PRIVATE);
        if (prefs.getBoolean("asked_notifications", false)) return;
        prefs.edit().putBoolean("asked_notifications", true).apply();
        ActivityCompat.requestPermissions(this, new String[] { Manifest.permission.POST_NOTIFICATIONS }, 1001);
    }
}
