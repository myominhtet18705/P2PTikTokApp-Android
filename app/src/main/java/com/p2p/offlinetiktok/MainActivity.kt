package com.p2p.offlinetiktok

import android.annotation.SuppressLint
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var spinner: ProgressBar
    private lateinit var statusText: TextView

    private val serverUrl = "http://127.0.0.1:5000"
    private var serverStarted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        spinner = findViewById(R.id.loadingSpinner)
        statusText = findViewById(R.id.loadingText)

        setupWebView()
        startPythonServer()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.settings.databaseEnabled = true
        webView.settings.setSupportMultipleWindows(false)

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                spinner.visibility = View.GONE
                webView.visibility = View.VISIBLE
            }

            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                super.onReceivedError(view, errorCode, description, failingUrl)
                Log.e("P2PTikTok", "WebView error: $description at $failingUrl")
                runOnUiThread {
                    statusText.text = "Connection error:\n$description"
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                runOnUiThread { request.grant(request.resources) }
            }
        }
    }

    /** Starts Chaquopy's embedded Python, then calls flask_server.main() on a
     *  background thread so the Flask dev server doesn't block the UI thread. */
    private fun startPythonServer() {
        Thread {
            try {
                // Use applicationContext to avoid Activity context memory leaks
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(applicationContext))
                }

                val py = Python.getInstance()
                val module = py.getModule("flask_server")

                // Point the app's Flask code at Android's private, writable storage
                val dataDir = File(filesDir, "p2p_data")
                if (!dataDir.exists()) dataDir.mkdirs()
                System.setProperty("APP_DATA_DIR", dataDir.absolutePath)

                // Set via Python's own os module
                val os = py.getModule("os")
                os.get("environ")!!.callAttr("__setitem__", "APP_DATA_DIR", dataDir.absolutePath)

                Log.i("P2PTikTok", "Starting Flask server...")
                module.callAttr("main")
            } catch (e: Exception) {
                Log.e("P2PTikTok", "Server failed to start", e)
                runOnUiThread {
                    statusText.text = "Server failed:\n${e.message}"
                }
            }
        }.start()

        waitForServerThenLoad()
    }

    /** Polls localhost:5000 until Flask responds, then loads it into the WebView. */
    private fun waitForServerThenLoad() {
        Thread {
            var attempts = 0
            while (!serverStarted && attempts < 120) {
                try {
                    val conn = URL(serverUrl).openConnection() as HttpURLConnection
                    conn.connectTimeout = 1000
                    conn.readTimeout = 1000
                    conn.requestMethod = "GET"
                    val code = conn.responseCode
                    if (code in 200..499) {
                        serverStarted = true
                    }
                    conn.disconnect()
                } catch (e: Exception) {
                    // server not up yet, keep polling
                }
                if (!serverStarted) {
                    attempts++
                    Thread.sleep(500)
                }
            }

            runOnUiThread {
                if (serverStarted) {
                    webView.loadUrl(serverUrl)
                } else {
                    statusText.text = "Server did not start.\nPlease restart the app."
                    spinner.visibility = View.GONE
                }
            }
        }.start()
    }

    @Deprecated("Use OnBackPressedDispatcher")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
