#!/usr/bin/env bash

#-----------------------------------#
# NOTE: This script is experimental #
#-----------------------------------#

APP=".dist/LevityDash.app"
DMG_PATH=".dist/LevityDash_macOS.dmg"
ZIP_PATH=".dist/LevityDash_macOS.zip"
DMG_DIST_PATH="./dist/dmg"
SIGNATURE=""

# check signature
check_sig() {
	echo 1
		if [ -z "$SIGNATURE" ]; then
				echo "No signature provided, skipping code signing"
				echo "To sign, change the SIGNATURE variable in the script"
				exit 1
		fi
		echo "Using signature: $SIGNATURE"
		return 0
}

check_file_sig() {
		# check if ../.signature exists
		echo 2
		if [ ! -f "../.signature" ]; then
				echo "No signature file found, skipping code signing"
				return 0
		fi
		# check if signature is valid
		SIGNATURE=$(cat ../.signature)
		check_sig
}

# sign the app
sign_app() {
	echo "Signing app..."

	check_sig

	codesign --deep --force --options=runtime --entitlements ./entitlements.plist --sign "$SIGNATURE" --timestamp "$APP"
}

check_file_sig || check_sig || return 1

zip_app() {
	echo "Creating zip file..."
	ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP_PATH"
	echo "Zip file created at $ZIP_PATH"
}

notarize() {
	echo "Submitting to Apple for notarization..."
	xcrun notarytool submit --keychain-profile "noblecloud" --progress $ZIP_PATH
	echo "Submission complete, use 'xcrun notarytool history' to check status"
}

staple() {
	echo "Stapling notarization ticket to app..."
	xcrun stapler staple $APP
	echo "Stapled!"
}

build_dmg() {

	# test if create-dmg is installed
	if ! command -v create-dmg &> /dev/null
	then
		echo "create-dmg is required to build the dmg file"
		echo "install with: brew install create-dmg"
		exit 1
	fi

	echo "Building DMG..."

	# Ensure the temp dmg folder exists and is empty
	mkdir -p $DMG_DIST_PATH
	rm -rf "$DMG_DIST_PATH/*"

	# Copy the app into the temp dmg folder
	cp -r $APP $DMG_DIST_PATH

	# If the dmg already exists, remove it
	test -f "$DMG_PATH" && rm "$DMG_PATH"

	# Create the dmg
	create-dmg \
		--volname "LevityDash" \
		--volicon "assets/macOS.icns" \
		--window-pos 200 120 \
		--window-size 800 400 \
		--icon-size 100 \
		--icon "LevityDash.app" 200 190 \
		--hide-extension "LevityDash.app" \
		--app-drop-link 600 185 \
		"$DMG_PATH" \
		"$DMG_DIST_PATH"
	}
