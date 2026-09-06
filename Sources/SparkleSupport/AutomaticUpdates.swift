import Sparkle

/// Coordinates application updates from the release appcast.
///
/// The fork signs its own appcast with its own Ed25519 key (see the
/// `SPARKLE_PUBLIC_KEY` in the makefile) and publishes releases via
/// `make release GENERATE_APPCAST=1 PUBLISH=1`. The feed URL is the fork's
/// `releases/latest/download/appcast.xml`, never upstream's.
@MainActor
public enum AutomaticUpdates {
    private static let updaterController = SPUStandardUpdaterController(
        startingUpdater: true,
        updaterDelegate: nil,
        userDriverDelegate: nil,
    )

    /// Starts Sparkle's periodic update checks for the main application bundle.
    public static func start() {
        _ = updaterController
    }

    /// Displays Sparkle's standard update-checking interface.
    public static func checkForUpdates() {
        updaterController.checkForUpdates(nil)
    }
}
