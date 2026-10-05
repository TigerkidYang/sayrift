// Platform-free core: OpenRouter client, the dictation / translate / Ask pipeline, prompts, output guard.
// Plain Kotlin/JVM so it is unit-testable on the desktop and can move to Kotlin Multiplatform for iOS later.
plugins {
    `java-library`
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// Built with whatever JDK runs Gradle (21 here), emitting Java 17 bytecode for Android.
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

// One source of truth: the prompts are the desktop app's files, copied in at build time.
val copyPrompts by tasks.registering(Copy::class) {
    from(rootProject.file("../src/local_typeless/prompts")) { include("*.md") }
    into(layout.buildDirectory.dir("generated/prompts/app/localtypeless/core/prompts"))
}
sourceSets["main"].resources.srcDir(layout.buildDirectory.dir("generated/prompts"))
tasks.named("processResources") { dependsOn(copyPrompts) }

dependencies {
    api("com.squareup.okhttp3:okhttp:4.12.0") // OkHttpClient is part of OpenRouterClient's constructor
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    testImplementation(kotlin("test"))
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

tasks.test { useJUnitPlatform() }
