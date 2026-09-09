package dev.codexcrew.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;
import android.webkit.ValueCallback;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.ProgressBar;
import android.widget.FrameLayout;

/** The gateway owns the dashboard, login, authorization and responsive layout. */
public class MainActivity extends Activity {
    private LinearLayout root;
    private WebView web;
    private String origin;
    private ValueCallback<Uri[]> fileSelection;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        WebView.setWebContentsDebuggingEnabled(
                (getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::navigateBack);
        }
        origin = getPreferences(MODE_PRIVATE).getString("origin", "");
        showConnection();
        String proposed = getIntent().getStringExtra("dashboard_url");
        if (proposed != null) propose(proposed);
        else if (!origin.isEmpty()) openDashboard(origin);
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String proposed = intent.getStringExtra("dashboard_url");
        if (proposed != null) propose(proposed);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void frame() {
        if (fileSelection != null) {
            fileSelection.onReceiveValue(null);
            fileSelection = null;
        }
        if (web != null) {
            web.stopLoading();
            web.destroy();
            web = null;
        }
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setFitsSystemWindows(true);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else {
                v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets;
        });
        setContentView(root);
    }

    private Button button(LinearLayout container, int label, Runnable action) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(v -> action.run());
        container.addView(button, new LinearLayout.LayoutParams(-1, -2));
        return button;
    }

    private void paragraph(LinearLayout container, int text, int size) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setPadding(0, dp(12), 0, dp(12));
        container.addView(view, new LinearLayout.LayoutParams(-1, -2));
    }

    private void showConnection() {
        frame();
        ScrollView scroll = new ScrollView(this);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, -1));
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(20), dp(16), dp(20), dp(20));
        scroll.addView(content);
        paragraph(content, R.string.connect_title, 26);
        paragraph(content, R.string.connect_help, 16);
        EditText address = new EditText(this);
        address.setHint(R.string.address_hint);
        address.setContentDescription(getString(R.string.address_hint));
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setText(origin);
        content.addView(address, new LinearLayout.LayoutParams(-1, -2));
        button(content, R.string.connect, () -> {
            try { openDashboard(ConnectionAddress.parse(address.getText().toString())); }
            catch (IllegalArgumentException ex) { address.setError(getString(R.string.invalid_address)); }
        });
        button(content, R.string.pairing, this::pairingHelp);
        button(content, R.string.forget, () -> {
            origin = "";
            getPreferences(MODE_PRIVATE).edit().clear().apply();
            CookieManager.getInstance().removeAllCookies(ok -> CookieManager.getInstance().flush());
            WebStorage.getInstance().deleteAllData();
            WebView cleanup = new WebView(this);
            cleanup.clearCache(true);
            cleanup.clearHistory();
            cleanup.destroy();
            address.setText("");
        });
    }

    private void propose(String value) {
        final String target;
        try { target = ConnectionAddress.parse(value); }
        catch (IllegalArgumentException ex) { return; }
        // Exported launcher extras cannot silently replace a trusted connection.
        new AlertDialog.Builder(this).setTitle(R.string.new_connection).setMessage(target)
                .setPositiveButton(R.string.open, (d, w) -> openDashboard(target))
                .setNegativeButton(R.string.cancel, null).show();
    }

    private void pairingHelp() {
        new AlertDialog.Builder(this).setTitle(R.string.pairing)
                .setItems(new String[] {getString(R.string.pairing_steps), getString(R.string.auto_blocker)},
                        (d, which) -> { if (which == 0) pairingSteps(); else autoBlockerHelp(); })
                .setNegativeButton(R.string.cancel, null).show();
    }

    private void autoBlockerHelp() {
        new AlertDialog.Builder(this).setTitle(R.string.auto_blocker).setMessage(R.string.auto_blocker_help)
                .setPositiveButton(R.string.security_settings, (d, w) -> {
                    try { startActivity(new Intent(Settings.ACTION_SECURITY_SETTINGS)); }
                    catch (android.content.ActivityNotFoundException ex) {
                        try { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
                        catch (android.content.ActivityNotFoundException unavailable) {
                            new AlertDialog.Builder(this).setMessage(R.string.auto_blocker_help)
                                    .setPositiveButton(R.string.ok, null).show();
                        }
                    }
                }).setNegativeButton(R.string.cancel, null).show();
    }

    private void pairingSteps() {
        new AlertDialog.Builder(this).setTitle(R.string.pairing).setMessage(R.string.pairing_help)
                .setPositiveButton(R.string.developer_settings, (d, w) -> {
                    try { startActivity(new Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)); }
                    catch (android.content.ActivityNotFoundException ex) {
                        new AlertDialog.Builder(this).setMessage(R.string.settings_unavailable)
                                .setPositiveButton(R.string.ok, null).show();
                    }
                }).setNegativeButton(R.string.cancel, null).show();
    }

    private void openDashboard(String address) {
        origin = ConnectionAddress.parse(address);
        getPreferences(MODE_PRIVATE).edit().putString("origin", origin).apply();
        frame();
        TextView error = new TextView(this);
        error.setText(R.string.load_failed);
        error.setTextSize(16);
        error.setPadding(dp(16), dp(8), dp(16), dp(8));
        error.setVisibility(View.GONE);
        root.addView(error);
        Button retry = button(root, R.string.retry, () -> { if (web != null) web.reload(); });
        retry.setVisibility(View.GONE);
        ProgressBar loading = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        root.addView(loading, new LinearLayout.LayoutParams(-1, dp(3)));
        web = new WebView(this);
        FrameLayout dashboard = new FrameLayout(this);
        root.addView(dashboard, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        dashboard.addView(web, new FrameLayout.LayoutParams(-1, -1));
        FloatingConnectionButton connection = new FloatingConnectionButton(
                this, dashboard, getPreferences(MODE_PRIVATE), this::showConnection);
        dashboard.addView(connection, new FrameLayout.LayoutParams(dp(48), dp(48)));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setSafeBrowsingEnabled(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int progress) {
                loading.setProgress(progress);
                loading.setVisibility(progress < 100 ? View.VISIBLE : View.GONE);
            }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                if (fileSelection != null) fileSelection.onReceiveValue(null);
                fileSelection = callback;
                Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                picker.addCategory(Intent.CATEGORY_OPENABLE);
                picker.setType("*/*");
                picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try { startActivityForResult(picker, 1); }
                catch (android.content.ActivityNotFoundException ex) {
                    fileSelection.onReceiveValue(null);
                    fileSelection = null;
                }
                return true;
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String target = request.getUrl().toString();
                debug("navigation same-origin=" + ConnectionAddress.sameOrigin(origin, target));
                if (ConnectionAddress.sameOrigin(origin, target)) return false;
                if (request.isForMainFrame() && request.hasGesture()
                        && "https".equals(request.getUrl().getScheme())) {
                    new AlertDialog.Builder(MainActivity.this).setTitle(R.string.external_link)
                            .setMessage(request.getUrl().getHost())
                            .setPositiveButton(R.string.open, (d, w) -> {
                                try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(target))); }
                                catch (android.content.ActivityNotFoundException ignored) { }
                            }).setNegativeButton(R.string.cancel, null).show();
                }
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                debug("page started");
                error.setVisibility(View.GONE);
                retry.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError failure) {
                debug("load error=" + failure.getErrorCode());
                if (request.isForMainFrame()) {
                    error.setVisibility(View.VISIBLE);
                    retry.setVisibility(View.VISIBLE);
                }
            }
            @Override public void onPageFinished(WebView view, String url) {
                debug("page finished");
                if (ConnectionAddress.sameOrigin(origin, url)) {
                    // Native-client presentation only; preserve keyboard focus indication.
                    view.evaluateJavascript("(() => { let s = document.getElementById('crew-native-style');"
                            + "if (!s) { s = document.createElement('style'); s.id = 'crew-native-style'; document.head.appendChild(s); }"
                            + "s.textContent = 'header.topbar button:has(> svg.lucide-settings) { border: 0 !important; box-shadow: none !important; background: transparent !important; } header.topbar button:has(> svg.lucide-settings):focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }'; })()", null);
                }
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request,
                    android.webkit.WebResourceResponse response) {
                debug("HTTP status=" + response.getStatusCode());
                if (request.isForMainFrame() && response.getStatusCode() >= 500) {
                    error.setVisibility(View.VISIBLE);
                    retry.setVisibility(View.VISIBLE);
                }
            }
            @Override public void onReceivedSslError(WebView view, android.webkit.SslErrorHandler handler,
                    android.net.http.SslError sslError) {
                handler.cancel();
                debug("TLS error=" + sslError.getPrimaryError());
                error.setVisibility(View.VISIBLE);
                retry.setVisibility(View.VISIBLE);
            }
        });
        web.loadUrl(origin);
    }

    private void debug(String message) {
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0)
            android.util.Log.d("CrewMobile", message);
    }

    private void navigateBack() {
        if (web != null && web.canGoBack()) web.goBack();
        else if (web != null) showConnection();
        else finish();
    }

    // API 33+ uses the native OnBackInvokedDispatcher registered in onCreate.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() {
        navigateBack();
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 1 && fileSelection != null) {
            Uri[] selected = WebChromeClient.FileChooserParams.parseResult(result, data);
            // Accept only the content URIs returned by Android's document picker.
            if (selected != null) for (Uri uri : selected) {
                if (!"content".equals(uri.getScheme())) { selected = null; break; }
            }
            fileSelection.onReceiveValue(selected);
            fileSelection = null;
        }
    }

    @Override protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
