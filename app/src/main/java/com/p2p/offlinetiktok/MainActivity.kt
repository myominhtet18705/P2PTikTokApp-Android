package com.p2p.offlinetiktok

import android.annotation.SuppressLint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            databaseEnabled = true
            setSupportMultipleWindows(false)
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }

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
                Handler(Looper.getMainLooper()).post {
                    statusText.text = "Connection error:\n$description"
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                Handler(Looper.getMainLooper()).post { request.grant(request.resources) }
            }
        }
    }

    /**
     * PyApplication (declared in AndroidManifest.xml) already calls Python.start()
     * automatically when the process starts. So we just need to verify it's running.
     */
    private fun startPythonServer() {
        Thread {
            try {
                // PyApplication should have already started Python
                if (!Python.isStarted()) {
                    Log.e("P2PTikTok", "Python was NOT started by PyApplication! Attempting manual start...")
                    try {
                        Python.start(com.chaquo.python.android.AndroidPlatform(applicationContext))
                        Log.i("P2PTikTok", "Manual Python start succeeded")
                    } catch (e: Exception) {
                        Log.e("P2PTikTok", "Manual Python start failed", e)
                        Handler(Looper.getMainLooper()).post {
                            statusText.text = "Fatal: Cannot start Python runtime.\n${e.message}"
                            spinner.visibility = View.GONE
                        }
                        return@Thread
                    }
                } else {
                    Log.i("P2PTikTok", "Python already started by PyApplication")
                }

                val py = Python.getInstance()
                val dataDir = File(filesDir, "p2p_data")
                if (!dataDir.exists()) dataDir.mkdirs()

                System.setProperty("APP_DATA_DIR", dataDir.absolutePath)
                val os = py.getModule("os")
                os.get("environ")!!.callAttr("__setitem__", "APP_DATA_DIR", dataDir.absolutePath)

                Log.i("P2PTikTok", "Importing flask_server module...")
                val module = py.getModule("flask_server")

                Log.i("P2PTikTok", "Starting Flask server...")
                module.callAttr("main")
            } catch (e: Exception) {
                Log.e("P2PTikTok", "Server failed to start", e)
                Handler(Looper.getMainLooper()).post {
                    statusText.text = "Server failed:\n${e.message ?: "Unknown error"}\n\nCheck Logcat for details."
                    spinner.visibility = View.GONE
                }
            }
        }.start()

        waitForServerThenLoad()
    }

    /**
     * Polls localhost:5000 until Flask responds, then loads it into the WebView.
     */
    private fun waitForServerThenLoad() {
        Thread {
            var attempts = 0
            val maxAttempts = 240 // 2 minutes for slower devices
            while (!serverStarted && attempts < maxAttempts) {
                try {
                    val conn = URL(serverUrl).openConnection() as HttpURLConnection
                    conn.connectTimeout = 2000
                    conn.readTimeout = 2000
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

            Handler(Looper.getMainLooper()).post {
                if (serverStarted) {
                    webView.loadUrl(serverUrl)
                } else {
                    statusText.text = "Server did not start in time.\nPlease restart the app."
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
