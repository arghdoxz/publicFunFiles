# AIC8800 WiFi+BT Setup — Orange Pi 5 Armbian (kernel 6.1.x-vendor-rk35xx)

Survives `apt upgrade` via DKMS auto-rebuild. Boots without delay via event-driven udev.

---

## Clean Slate

Remove any prior manual installs to avoid conflicts with the DKMS-managed setup.

```bash
sudo dkms remove aic8800-usb/4.0 --all 2>/dev/null || true
sudo apt remove --purge aic8800-usb-dkms aic8800-firmware -y 2>/dev/null || true
sudo rm -rf /usr/src/aic8800-usb-4.0
sudo rm -rf /var/lib/dkms/aic8800-usb
sudo rm -f /lib/modules/$(uname -r)/updates/dkms/aic_load_fw_usb.ko
sudo rm -f /lib/modules/$(uname -r)/updates/dkms/aic8800_fdrv_usb.ko
sudo rm -f /lib/modules/$(uname -r)/updates/dkms/aic_btusb_usb.ko
```

---

## Step 1: System Packages

Install build tools, kernel headers, DKMS, and NetworkManager.
`dkms` is what auto-rebuilds the driver whenever `apt upgrade` installs a new kernel.
`linux-headers-vendor-rk35xx` must match the BSP kernel (`uname -r`) — DKMS needs it to compile against.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git dkms usb-modeswitch linux-headers-vendor-rk35xx network-manager
```

---

## Step 2: Clone Driver Source

Clones the driver from the `bluetooth` branch which includes both WiFi and BT support for the AIC8800D80 chip.

```bash
cd /tmp
git clone --branch bluetooth --depth 1 https://github.com/shenmintao/aic8800d80.git aic8800d80-bt
```

---

## Step 3: Install Firmware

Copies the device firmware blobs to `/lib/firmware` where the kernel driver looks for them at load time.
The symlink ensures the driver finds firmware at its expected path regardless of naming differences.

```bash
sudo cp -r /tmp/aic8800d80-bt/fw/aic8800D80 /lib/firmware/

sudo mkdir -p /lib/firmware/aic8800_fw/USB
sudo ln -sf /lib/firmware/aic8800D80 /lib/firmware/aic8800_fw/USB/aic8800D80 2>/dev/null || true
```

---

## Step 4: Register Driver with DKMS

DKMS manages out-of-tree kernel modules. Registering the driver here means it will be automatically
rebuilt and reinstalled into the correct `/lib/modules/$(uname -r)/` path after every kernel update —
no manual intervention needed. `AUTOINSTALL="yes"` in `dkms.conf` is what triggers the auto-rebuild.

```bash
DKMS_SRC="/usr/src/aic8800-usb-4.0"
sudo cp -r /tmp/aic8800d80-bt/drivers/aic8800 ${DKMS_SRC}

sudo tee ${DKMS_SRC}/dkms.conf << 'EOF'
PACKAGE_NAME="aic8800-usb"
PACKAGE_VERSION="4.0"

# Module 0: firmware loader — built from aic_load_fw/, installed as aic_load_fw_usb.ko
BUILT_MODULE_NAME[0]="aic_load_fw"
BUILT_MODULE_LOCATION[0]="aic_load_fw/"
DEST_MODULE_NAME[0]="aic_load_fw_usb"
DEST_MODULE_LOCATION[0]="/updates/dkms/"

# Module 1: main WiFi/BT driver — built from aic8800_fdrv/, installed as aic8800_fdrv_usb.ko
BUILT_MODULE_NAME[1]="aic8800_fdrv"
BUILT_MODULE_LOCATION[1]="aic8800_fdrv/"
DEST_MODULE_NAME[1]="aic8800_fdrv_usb"
DEST_MODULE_LOCATION[1]="/updates/dkms/"

MAKE[0]="make KVER=${kernelver}"
CLEAN="make clean"

# Automatically rebuild and reinstall when a new kernel is installed via apt
AUTOINSTALL="yes"
EOF

# Build and install for the currently running kernel
sudo dkms add aic8800-usb/4.0
sudo dkms build aic8800-usb/4.0
sudo dkms install aic8800-usb/4.0

# Confirm: should show "aic8800-usb/4.0, <kernelver>, aarch64: installed"
sudo dkms status
```

---

## Step 5: Udev Helper Script

This script is called by udev after the device finishes modeswitching from USB storage to WiFi mode (368b:8d81).
`modprobe` is synchronous — it returns only after the module is fully loaded — so no sleeps are needed.
This replaces the old systemd service and its hardcoded 6-second sleep delay entirely.

```bash
sudo tee /usr/local/bin/aic8800-bind.sh << 'EOF'
#!/bin/bash
# Load firmware loader first, then the main driver
modprobe aic_load_fw_usb
modprobe aic8800_fdrv_usb
# Register the post-modeswitch USB ID so the driver binds to the device
echo "368b 8d81" > /sys/bus/usb/drivers/aic8800_fdrv/new_id 2>/dev/null || true
EOF
sudo chmod +x /usr/local/bin/aic8800-bind.sh
```

---

## Step 6: Udev Rules

Two rules handle the full plug-in sequence as two distinct USB events:
- Rule 1 fires on plug: device appears as USB mass-storage (a69c:5721) → modeswitch triggers, device re-enumerates
- Rule 2 fires after re-enumeration: device now appears as WiFi adapter (368b:8d81) → modules load and bind

This is fully event-driven. No polling, no service, no fixed delays — the driver is ready
as fast as the hardware allows.

```bash
sudo tee /etc/udev/rules.d/50-aic8800.rules << 'EOF'
# Step 1: Device plugged in as USB mass-storage → switch it to WiFi/BT mode
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="a69c", ATTR{idProduct}=="5721", \
  RUN+="/usr/bin/usb_modeswitch -v 0xa69c -p 0x5721 -KQ"

# Step 2: Device re-enumerated as WiFi adapter → load kernel modules and bind driver
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="368b", ATTR{idProduct}=="8d81", \
  RUN+="/usr/local/bin/aic8800-bind.sh"
EOF

# Prevent usb-storage from grabbing the device before modeswitch runs
echo 'options usb-storage quirks=a69c:5721:i' | sudo tee /etc/modprobe.d/usb-storage-aic.conf

# Remove any old blacklists that may block bt/wifi modules from loading
sudo rm -f /etc/modprobe.d/blacklist-btusb.conf
sudo rm -f /etc/modprobe.d/blacklist-aic-btusb.conf
sudo rm -f /etc/modprobe.d/blacklist-aic-sdio.conf

sudo udevadm control --reload-rules
sudo depmod -a
```

---

## Step 7: Boot Time Optimizations

Mask services that add significant delay to boot but are not needed on this board.

```bash
# systemd-rfkill waits for radio kill switches to settle — not applicable here, saves ~11s
sudo systemctl mask systemd-rfkill.service
sudo systemctl mask systemd-rfkill.socket

# Blocks boot until network is fully up — unnecessary for desktop use
sudo systemctl mask NetworkManager-wait-online.service

# Boot splash screen — minor save, also cleaner for debugging
sudo systemctl mask plymouth-start.service
sudo systemctl mask plymouth-quit-wait.service

# RPC services — only needed for NFS, not applicable here
sudo systemctl disable rpcbind.service
sudo systemctl mask rpc-statd-notify.service

# Background package management daemon — starts on boot, wastes resources
sudo systemctl disable packagekit.service

# Location services — not needed
sudo systemctl disable geoclue.service

sudo systemctl daemon-reload
```

To see what's still eating boot time after reboot:
```bash
systemd-analyze blame | head -20
systemd-analyze critical-chain
```

---

## Step 8: Reboot & Verify

```bash
sudo reboot
```

After reboot:

```bash
# Confirm DKMS installed modules correctly for the running kernel
dkms status

# WiFi — wlx... interface should appear and be manageable via nmcli
ip link show | grep wl
sudo nmcli dev wifi connect "YourSSID" password "YourPassword"
sudo ping -c 3 8.8.8.8

# Bluetooth — should show UP RUNNING with a real MAC address
hciconfig -a
bluetoothctl show
```

**Expected results:**
- `dkms status` → `aic8800-usb/4.0, <kernelver>, aarch64: installed`
- WiFi: `wlx...` interface present, connects to SSID, ping succeeds
- BT: `hciconfig` shows `UP RUNNING`, `bluetoothctl show` shows controller with real MAC

---

## After Any Future Kernel Update

DKMS handles this automatically. But if something goes wrong (e.g. headers weren't installed when the kernel updated), rebuild manually:

```bash
sudo apt install -y linux-headers-vendor-rk35xx  # ensure headers match current kernel
sudo dkms build aic8800-usb/4.0 -k $(uname -r)
sudo dkms install aic8800-usb/4.0 -k $(uname -r)
sudo reboot
```
