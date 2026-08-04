package com.p2p.offlinetiktok

import android.util.Log
import com.chaquo.python.android.PyApplication

class App : PyApplication() {
    override fun onCreate() {
        // Set up global crash handler
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e("P2PTikTok_App", "FATAL CRASH in thread: " + thread.name, throwable)
            try {
                val crashFile = java.io.File(filesDir, "last_crash.txt")
                crashFile.writeText(
                    "CRASH at " + System.currentTimeMillis() + "\n" +
                    "Thread: " + thread.name + "\n" +
                    "Error: " + throwable.javaClass.name + ": " + throwable.message + "\n" +
                    "Stack: " + Log.getStackTraceString(throwable) + "\n"
                )
            } catch (e: Exception) { }
        }

        Log.i("P2PTikTok_App", "App.onCreate() - initializing Python...")
        try {
            super.onCreate()
            Log.i("P2PTikTok_App", "Python started successfully")
        } catch (e: Throwable) {
            Log.e("P2PTikTok_App", "FATAL: Python.start() failed", e)
            try {
                java.io.File(filesDir, "last_crash.txt").appendText(
                    "PYTHON START FAILED: " + e.javaClass.name + ": " + e.message + "\n" +
                    "Stack: " + Log.getStackTraceString(e) + "\n"
                )
            } catch (ignored: Exception) { }
            throw e
        }
    }
}
