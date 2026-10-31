package io.github.johncarter2021.sidee

import android.app.Activity
import android.content.Context
import android.net.wifi.WifiManager
import android.os.Bundle
import android.util.Log
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Spike Activity: start the shared Python dashboard on loopback and
 * load it in a WebView that refuses every non-loopback URL. The
 * WebView is never a general browser: tile URLs are sent to the TV
 * by the dashboard code, never opened here.
 */
class MainActivity : Activity() {
    private var webView: WebView? = null
    private var multicastLock: WifiManager.MulticastLock? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        // Private storage only: session and TV certificates never
        // leave the app's files directory.
        val url = Python.getInstance()
            .getModule("sidee_android")
            .callAttr("start", filesDir.absolutePath)
            .toString()
        // Log the port, never the key: the full URL stays in-process.
        Log.i("Sidee", "Sidee dashboard started on port " + url.substringAfter(":").substringBefore("/"))
        val view = WebView(this)
        view.settings.javaScriptEnabled = true
        view.settings.domStorageEnabled = true
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean {
                val host = request?.url?.host ?: return true
                // Loopback only. Anything else is blocked, not loaded.
                return host != "127.0.0.1" && host != "localhost"
            }
        }
        view.loadUrl(url)
        webView = view
        setContentView(view)
    }

    override fun onResume() {
        super.onResume()
        // SSDP discovery will not hear the TV on many phones without
        // a Wi-Fi multicast lock.
        val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val lock = wifi.createMulticastLock("sidee-discovery")
        lock.setReferenceCounted(true)
        lock.acquire()
        multicastLock = lock
    }

    override fun onPause() {
        multicastLock?.let {
            if (it.isHeld) it.release()
        }
        multicastLock = null
        super.onPause()
    }

    override fun onDestroy() {
        webView?.destroy()
        webView = null
        super.onDestroy()
    }
}
