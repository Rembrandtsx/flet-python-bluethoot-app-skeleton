import "package:flet/flet.dart";
import "package:flutter/widgets.dart";

import "flet_ble_bridge_service.dart";

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FletBleBridge":
        return FletBleBridgeService(control: control);
      default:
        return null;
    }
  }
}
