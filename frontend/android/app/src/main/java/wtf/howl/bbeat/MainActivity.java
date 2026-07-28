package wtf.howl.bbeat;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(BbeatAutoPlugin.class);
        registerPlugin(BbeatUpdaterPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
