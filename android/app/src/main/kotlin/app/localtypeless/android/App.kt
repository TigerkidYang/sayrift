package app.localtypeless.android

import android.app.Application

class App : Application() {
    lateinit var prefs: Prefs
        private set
    lateinit var store: Store
        private set

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        store = Store(this)
        Dictation.app = this
        prefs.migrateHistory(store)
        store.prune(prefs.keepDays)
    }
}
