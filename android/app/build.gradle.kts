plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "io.github.johncarter2021.sidee"
    compileSdk = 34

    defaultConfig {
        // Spike application ID (fork owner). A release identifier is
        // still an open decision; see android/README.md.
        applicationId = "io.github.johncarter2021.sidee"
        minSdk = 24
        targetSdk = 34
        versionCode = 3
        versionName = "0.2.0.1"
        ndk {
            // Chaquopy ABIs: arm64 for phones, x86_64 for emulators.
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

chaquopy {
    defaultConfig {
        // Chaquopy 16 supports up to 3.13; 3.11 is chosen for the
        // widest wheel availability. paho-mqtt is pure Python.
        version = "3.11"
        pip {
            install("paho-mqtt==2.1.0")
        }
        // Keep .py sources in the spike APK so stack traces are
        // readable; startup speed is not the spike's question.
        pyc {
            src = false
        }
    }
}

// Copy the shared Python core and image assets into the Chaquopy
// source tree at build time, instead of committing a second copy
// that would drift. The generated tree is gitignored; only
// sidee_android.py is committed under app/src/main/python.
//
// NOTE: this must stay as TWO tasks with one from/into each. A
// single Copy task with two into() calls silently sends BOTH
// sources to the LAST destination (Gradle's into() is task-level,
// not scoped to the preceding from()) — that bug shipped run #19,
// where core/*.py landed under assets/ and the app crashed on
// launch with ModuleNotFoundError: No module named 'core'.
val copyCore = tasks.register<Copy>("copyCore") {
    from("../../core") {
        include("*.py")
        include("dashboard.html")
        include("tv-client.bundle")
    }
    into("src/main/python/core")
    doLast {
        // Fail the build here, not at app launch, if the copy is wrong.
        require(file("src/main/python/core/webui.py").exists()) {
            "copyCore did not produce src/main/python/core/webui.py"
        }
        require(file("src/main/python/core/__init__.py").exists()) {
            "copyCore did not produce src/main/python/core/__init__.py"
        }
    }
}

val copyAssets = tasks.register<Copy>("copyAssets") {
    from("../../assets") {
        include("*.png")
    }
    into("src/main/python/assets")
}

tasks.named("preBuild") {
    dependsOn(copyCore, copyAssets)
}

// Chaquopy's merge task consumes the copied core tree, so it must
// declare the dependency explicitly: Gradle's task-dependency
// validation fails otherwise (run #14: mergeDebugPythonSources
// used copyCore's output with no declared dependency).
tasks.matching { it.name.endsWith("PythonSources") }.configureEach {
    dependsOn(copyCore, copyAssets)
}

dependencies {
}
