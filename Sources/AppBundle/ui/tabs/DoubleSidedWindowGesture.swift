import AppKit

private let doubleSidedWindowEventCallback: CGEventTapCallBack = { proxy, type, event, _ in
    // The tap is attached only to the main run loop. These borrowed values stay
    // on that thread for the synchronous callback; neither crosses a task boundary.
    nonisolated(unsafe) let mainThreadProxy = proxy
    nonisolated(unsafe) let mainThreadEvent = event
    let consumed = MainActor.assumeIsolated {
        DoubleSidedWindowGesture.shared.handle(proxy: mainThreadProxy, type: type, event: mainThreadEvent)
    }
    return consumed ? nil : Unmanaged.passUnretained(event)
}

/// Holds an Option-click until release so controls underneath do not receive the click.
@MainActor
final class DoubleSidedWindowGesture {
    static let shared = DoubleSidedWindowGesture()
    private var tap: CFMachPort?
    private var source: CFRunLoopSource?
    private var isTabHeld = false
    private var pending: (windowId: UInt32, down: CGEvent)?

    func install() {
        guard tap == nil else { return }
        let mask = [.leftMouseDown, .leftMouseDragged, .leftMouseUp, .keyDown, .keyUp].reduce(CGEventMask(0)) {
            $0 | (1 << ($1 as CGEventType).rawValue)
        }
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap, place: .headInsertEventTap, options: .defaultTap,
            eventsOfInterest: mask, callback: doubleSidedWindowEventCallback, userInfo: nil
        ), let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        else {
            debugFocusLog("doubleSidedWindows.eventTapUnavailable")
            return
        }
        self.tap = tap
        self.source = source
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
    }

    func handle(proxy: CGEventTapProxy, type: CGEventType, event: CGEvent) -> Bool {
        // Consumed events never reach the NSEvent monitors that cancel modifier-only
        // launchers. Cancel here before swallowing Option-Tab or an Option-click.
        if type == .keyDown || type == .leftMouseDown {
            noteTapBindingKeyDown()
        }
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            pending?.down.tapPostEvent(proxy)
            pending = nil
            isTabHeld = false
            if let tap { CGEvent.tapEnable(tap: tap, enable: true) }
            return false
        }
        switch type {
            case .keyDown, .keyUp:
                return handleKeyboard(type: type, event: event)
            case .leftMouseDown:
                pending = nil
                guard TrayMenuModel.shared.isEnabled,
                      ExperimentalUISettings().doubleSidedWindows,
                      event.flags.intersection([.maskAlternate, .maskCommand, .maskControl, .maskShift]) == .maskAlternate,
                      !DoubleSidedWindowController.shared.isAnimating,
                      let id = windowId(at: event.location),
                      let down = event.copy()
                else { return false }
                pending = (id, down)
                return true
            case .leftMouseDragged:
                guard let pending else { return false }
                guard doubleSidedClickMoved(from: pending.down.location, to: event.location) else { return true }
                // Post downstream before forwarding this drag. Native title-bar dragging
                // and the existing group-drag driver then receive a complete gesture.
                pending.down.tapPostEvent(proxy)
                self.pending = nil
                return false
            case .leftMouseUp:
                guard let pending else { return false }
                self.pending = nil
                guard TrayMenuModel.shared.isEnabled,
                      event.flags.contains(.maskAlternate),
                      !doubleSidedClickMoved(from: pending.down.location, to: event.location),
                      let window = Window.get(byId: pending.windowId),
                      window.nearestWindowTabGroup?.usesDoubleSidedWindows == true
                else {
                    pending.down.tapPostEvent(proxy)
                    return false
                }
                // Capture and animate outside the event tap to avoid timing out mouse input.
                Task { @MainActor in DoubleSidedWindowController.shared.flip(window) }
                return true
            default:
                return false
        }
    }

    private func handleKeyboard(type: CGEventType, event: CGEvent) -> Bool {
        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)
        guard keyCode == 48 else { return false } // macOS virtual key code for Tab.
        if type == .keyUp {
            let consumed = isTabHeld
            isTabHeld = false
            return consumed
        }
        if isTabHeld { return true }
        guard isDoubleSidedFlipShortcut(keyCode: keyCode, flags: event.flags),
              TrayMenuModel.shared.isEnabled,
              ExperimentalUISettings().doubleSidedWindows,
              let window = nativeFocusedPairWindow()
        else { return false }
        isTabHeld = true
        if event.getIntegerValueField(.keyboardEventAutorepeat) == 0,
           !DoubleSidedWindowController.shared.isAnimating {
            Task { @MainActor in DoubleSidedWindowController.shared.flip(window) }
        }
        return true
    }

    private func nativeFocusedPairWindow() -> Window? {
        guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
        // Read native focus so settings, dialogs, and other unpaired windows keep Option-Tab.
        let element = AXUIElementCreateApplication(app.processIdentifier)
        AXUIElementSetMessagingTimeout(element, 0.05)
        var focused: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, kAXFocusedWindowAttribute as CFString, &focused) == .success,
              let focused, CFGetTypeID(focused) == AXUIElementGetTypeID(),
              let id = (focused as! AXUIElement).containingWindowId(),
              let window = Window.get(byId: id),
              let group = window.nearestWindowTabGroup,
              group.usesDoubleSidedWindows, group.tabActiveWindow === window
        else { return nil }
        return window
    }

    private func windowId(at point: CGPoint) -> UInt32? {
        guard let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] else { return nil }
        return doubleSidedWindowId(at: point, in: windows)
    }
}

@MainActor
func doubleSidedWindowId(at point: CGPoint, in windows: [[String: Any]]) -> UInt32? {
    for info in windows {
        guard let bounds = info[kCGWindowBounds as String] as? [String: Any],
              let frame = CGRect(dictionaryRepresentation: bounds as CFDictionary), frame.contains(point),
              (info[kCGWindowAlpha as String] as? Double ?? 1) > 0,
              let id = info[kCGWindowNumber as String] as? UInt32
        else { continue }
        // Stop at the frontmost surface, even if it is an unmanaged window or menu.
        guard let window = Window.get(byId: id),
              let group = window.nearestWindowTabGroup,
              group.usesDoubleSidedWindows, group.tabActiveWindow === window
        else { return nil }
        return id
    }
    return nil
}

func doubleSidedClickMoved(from start: CGPoint, to end: CGPoint) -> Bool {
    hypot(end.x - start.x, end.y - start.y) > 4
}

func isDoubleSidedFlipShortcut(keyCode: Int64, flags: CGEventFlags) -> Bool {
    keyCode == 48 &&
        flags.intersection([.maskAlternate, .maskCommand, .maskControl, .maskShift]) == .maskAlternate
}
