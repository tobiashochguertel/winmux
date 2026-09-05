import AppBundle
import SwiftUI

// This file is shared between SPM and xcode project

@main
struct WinMuxApp: App {
    @StateObject var viewModel = TrayMenuModel.shared
    @StateObject var messageModel = MessageModel.shared
    @StateObject var shortcutSettingsModel = ShortcutSettingsModel.shared
    @Environment(\.openWindow) var openWindow: OpenWindowAction

    init() {
        // Fork builds never update via Sparkle: the fork publishes no
        // appcast, and upstream's feed must not reach fork users.
        initAppBundle()
    }

    var body: some Scene {
        menuBar(viewModel: viewModel)
        getShortcutSettingsWindow(model: shortcutSettingsModel)
            .onChange(of: shortcutSettingsModel.openRequestId) { _ in
                openShortcutSettingsWindow(openWindow)
            }
        getMessageWindow(messageModel: messageModel)
            .onChange(of: messageModel.message) { message in
                if message != nil {
                    openWindow(id: messageWindowId)
                }
            }
    }
}
