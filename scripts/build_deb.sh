#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('$DIR/pyproject.toml', 'rb'))['project']['version'])" 2>/dev/null || grep '^version = ' "$DIR/pyproject.toml" | cut -d'"' -f2 || echo "0.2.0")
ARCH="all"
PKG_DIR="$DIR/dist/deb/ulum_${VERSION}_${ARCH}"

echo "Building Debian package: ulum_${VERSION}_${ARCH}.deb..."

rm -rf "$DIR/dist/deb"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/lib/python3/dist-packages/ulum"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"

# Control file
cat << EOF > "$PKG_DIR/DEBIAN/control"
Package: ulum
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: ${ARCH}
Maintainer: Abdurrahman <levisdavid555@gmail.com>
Depends: python3 (>= 3.12), python3-rich, python3-typer, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1
Description: Universal Linux Update Manager
 Unified update manager and safe removal orchestrator for APT, Flatpak, Snap, and AppImage.
EOF

# Copy source code
cp -r "$DIR/src/ulum/"* "$PKG_DIR/usr/lib/python3/dist-packages/ulum/"
find "$PKG_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Binary wrappers
cat << 'EOF' > "$PKG_DIR/usr/bin/ulum"
#!/usr/bin/env bash
exec /usr/bin/python3 -m ulum.main "$@"
EOF
chmod +x "$PKG_DIR/usr/bin/ulum"

cat << 'EOF' > "$PKG_DIR/usr/bin/ulum-gui"
#!/usr/bin/env bash
export WEBKIT_DISABLE_DMABUF_RENDERER=1
export WEBKIT_DISABLE_COMPOSITING_MODE=1
exec /usr/bin/python3 -c "from ulum.gui.window import run_gui; run_gui()" "$@"
EOF
chmod +x "$PKG_DIR/usr/bin/ulum-gui"

# Desktop launcher
cp "$DIR/assets/ulum.desktop" "$PKG_DIR/usr/share/applications/ulum.desktop"

# Build package
dpkg-deb --build --root-owner-group "$PKG_DIR" "$DIR/dist/ulum_${VERSION}_${ARCH}.deb"
echo "✓ Successfully built: $DIR/dist/ulum_${VERSION}_${ARCH}.deb"
