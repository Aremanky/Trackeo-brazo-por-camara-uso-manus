#!/bin/bash
set -e  # Exit on error
set -u  # Exit on undefined variable

echo "=== Dependency Setup for Debian/Ubuntu ==="

echo "[1/1] Installing build dependencies..."
apt-get update
apt-get install -y \
    build-essential \
    cmake \
    libzmq3-dev \
    libncurses-dev \
    libudev-dev \
    libusb-1.0-0-dev

# Add read/write permissions for manus devices
if [ ! -f "/etc/udev/rules.d/70-manus-hid.rules" ]; then
    mkdir -p /etc/udev/rules.d/
    touch /etc/udev/rules.d/70-manus-hid.rules
    echo "[Setup] Adding read/write permissions for manus devices..."
    echo "# HIDAPI/libusb" >> /etc/udev/rules.d/70-manus-hid.rules
    echo "SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"3325\", MODE:=\"0666\"" >> /etc/udev/rules.d/70-manus-hid.rules
    echo "SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"1915\", ATTRS{idProduct}==\"83fd\", MODE:=\"0666\"" >> /etc/udev/rules.d/70-manus-hid.rules
    echo "# HIDAPI/hidraw" >> /etc/udev/rules.d/70-manus-hid.rules
    echo "KERNEL==\"hidraw*\", ATTRS{idVendor}==\"3325\", MODE:=\"0666\"" >> /etc/udev/rules.d/70-manus-hid.rules
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Udev rules have been configured to allow read/write access to manus devices."
echo "You may need to reload udev rules for the changes to take effect:"
echo "  sudo udevadm control --reload-rules"
echo "  sudo udevadm trigger"