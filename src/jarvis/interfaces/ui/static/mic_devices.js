(function () {
  "use strict";

  const STORAGE_KEY = "jarvis_mic_device_id";

  async function listInputDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
      return [];
    }
    let devices = await navigator.mediaDevices.enumerateDevices();
    let inputs = devices.filter((d) => d.kind === "audioinput");
    if (inputs.length && !inputs.some((d) => d.label)) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((t) => t.stop());
        devices = await navigator.mediaDevices.enumerateDevices();
        inputs = devices.filter((d) => d.kind === "audioinput");
      } catch (_) {}
    }
    return inputs.map((d) => ({
      deviceId: d.deviceId,
      label: d.label || ("Micro " + d.deviceId.slice(0, 8)),
    }));
  }

  window.JarvisMic = {
    getSelectedDeviceId() {
      try {
        return localStorage.getItem(STORAGE_KEY) || "";
      } catch (_) {
        return "";
      }
    },
    setSelectedDeviceId(deviceId) {
      try {
        if (deviceId) localStorage.setItem(STORAGE_KEY, deviceId);
        else localStorage.removeItem(STORAGE_KEY);
      } catch (_) {}
    },
    listInputDevices,
  };
})();
