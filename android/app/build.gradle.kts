import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Environment values override the untracked android/key.properties file, including blank values.
val signingProperties = Properties().apply {
    val localFile = rootProject.file("key.properties")
    if (localFile.isFile) localFile.reader(Charsets.UTF_8).use { load(it) }
}
val signingFields = linkedMapOf(
    "storeFile" to "SAYRIFT_SIGNING_STORE_FILE",
    "storePassword" to "SAYRIFT_SIGNING_STORE_PASSWORD",
    "keyAlias" to "SAYRIFT_SIGNING_KEY_ALIAS",
    "keyPassword" to "SAYRIFT_SIGNING_KEY_PASSWORD",
)
val signingValues = signingFields.mapValues { (property, environment) ->
    providers.environmentVariable(environment).orNull ?: signingProperties.getProperty(property)
}
val releaseKeystore = signingValues["storeFile"]?.takeIf { it.isNotBlank() }?.let { rootProject.file(it) }
val missingSigningFields = signingFields.filterKeys { signingValues[it].isNullOrBlank() }
val verifyReleaseSigning = tasks.register("verifyReleaseSigning") {
    group = "verification"
    description = "Check explicit release signing inputs without building an APK or requiring the Android SDK."
    doLast {
        if (missingSigningFields.isNotEmpty()) {
            throw GradleException(
                "Release signing is required; missing: " +
                    missingSigningFields.entries.joinToString { "${it.value} (${it.key})" } +
                    ". Set environment variables or android/key.properties; see android/signing.md. " +
                    "Release never falls back to debug signing. Use :app:assembleDebug for development.",
            )
        }
        if (releaseKeystore?.isFile != true || !releaseKeystore.canRead()) {
            throw GradleException(
                "Release keystore must be a readable file. Check SAYRIFT_SIGNING_STORE_FILE / storeFile; " +
                    "relative paths resolve from android/. See android/signing.md.",
            )
        }
    }
}

android {
    // Keep the installed app identity across the Sayrift rename; changing it would create a separate app.
    namespace = "app.localtypeless.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.localtypeless.android"
        minSdk = 29 // MediaRecorder writes OGG/Opus from Android 10: the same upload format as the desktop app
        targetSdk = 35
        versionCode = 3
        versionName = "0.2.1"
    }

    signingConfigs {
        create("release") {
            storeFile = releaseKeystore
            storePassword = signingValues["storePassword"]
            keyAlias = signingValues["keyAlias"]
            keyPassword = signingValues["keyPassword"]
        }
    }
    buildTypes {
        release {
            // R8 drops the unused icons of material-icons-extended: ~70 MB debug APK -> a few MB.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    packaging {
        resources {
            // Merge duplicate notices instead of dropping them, including AGP's default license exclusions.
            merges += setOf("/META-INF/{AL2.0,LGPL2.1,LICENSE*,NOTICE*}", "/{LICENSE*,NOTICE*}")
        }
    }
}

// Task dependencies cover aggregate, qualified and abbreviated invocations of APK/AAB builds.
tasks.matching { it.name == "preReleaseBuild" || it.name == "validateSigningRelease" }.configureEach {
    dependsOn(verifyReleaseSigning)
}

dependencies {
    implementation(project(":core"))
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended") // R8 strips the unused ones in release
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}

apply(from = rootProject.file("runtime-notices.gradle"))
