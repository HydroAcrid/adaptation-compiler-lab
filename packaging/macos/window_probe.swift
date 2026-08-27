import CoreGraphics
import Foundation

guard CommandLine.arguments.count == 2,
      let expectedPID = Int32(CommandLine.arguments[1]) else {
    fputs("usage: window_probe.swift <pid>\n", stderr)
    exit(2)
}

let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let values = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
        as? [[String: Any]] else {
    fputs("window list unavailable\n", stderr)
    exit(1)
}

let visible = values.contains { item in
    guard let pid = item[kCGWindowOwnerPID as String] as? Int32,
          pid == expectedPID,
          let layer = item[kCGWindowLayer as String] as? Int,
          layer == 0,
          let bounds = item[kCGWindowBounds as String] as? [String: Any],
          let width = bounds["Width"] as? Double,
          let height = bounds["Height"] as? Double else {
        return false
    }
    return width >= 720 && height >= 540
}

if visible {
    print("first_run_window_visible=true")
    exit(0)
}
fputs("Temper did not expose its first-run window\n", stderr)
exit(1)
