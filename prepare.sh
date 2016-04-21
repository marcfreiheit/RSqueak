#!/usr/bin/env bash

set -o errexit

readonly TEMPLATE_DIR="${TRAVIS_BUILD_DIR}/template"
readonly CONTENTS_DIR="${TEMPLATE_DIR}/RSqueak.app/Contents"
readonly RESOURCES_DIR="${CONTENTS_DIR}/Resources"
readonly IMAGE_TARGET="${RESOURCES_DIR}/RSqueak.image"
readonly CHANGES_TARGET="${RESOURCES_DIR}/RSqueak.changes"
readonly TARGET_TARGZ="${TRAVIS_BUILD_DIR}/RSqueak.tar.gz"
readonly TARGET_ZIP="${TRAVIS_BUILD_DIR}/RSqueak.zip"
readonly BASE_URL="https://www.hpi.uni-potsdam.de/hirschfeld/artefacts/rsqueak"
readonly TARGET_URL="${BASE_URL}/bundle/"
readonly VM_LINUX="rsqueak-linux-latest"
readonly VM_OSX="rsqueak-darwin-latest"
readonly VM_WIN="rsqueak-win32-latest.exe"
readonly VM_LINUX_TARGET="${CONTENTS_DIR}/Linux/RSqueak"
readonly VM_OSX_TARGET="${CONTENTS_DIR}/MacOS/RSqueak"
readonly VM_WIN_TARGET="${CONTENTS_DIR}/Win32/RSqueak.exe"

echo "Copying Squeak image into template..."
cp "${SMALLTALK_CI_IMAGE}" "${IMAGE_TARGET}"
cp "${SMALLTALK_CI_CHANGES}" "${CHANGES_TARGET}"
cp "${SMALLTALK_CI_BUILD}/"*.sources "${RESOURCES_DIR}/"

echo "Downloading latest VMs..."
curl -f -s --retry 3 -o "${VM_LINUX_TARGET}" "${BASE_URL}/${VM_LINUX}"
curl -f -s --retry 3 -o "${VM_OSX_TARGET}" "${BASE_URL}/${VM_OSX}"
curl -f -s --retry 3 -o "${VM_WIN_TARGET}" "${BASE_URL}/${VM_WIN}"

chmod 755 "${VM_LINUX_TARGET}" "${VM_OSX_TARGET}" "${VM_WIN_TARGET}"

VERSION="$(${VM_LINUX_TARGET} --git-version)"
sed -i "s/%VERSION%/${VERSION}/g" "${CONTENTS_DIR}/Info.plist"

echo "Compressing bundle..."
pushd "${TEMPLATE_DIR}" > /dev/null
tar czvf "${TARGET_TARGZ}" "./RSqueak.app"
zip -r "${TARGET_ZIP}" "./RSqueak.app"
popd > /dev/null

echo "Uploading files..."
curl -T "${TARGET_TARGZ}" -u "${DEPLOY_CREDENTIALS}" "${TARGET_URL}"
curl -T "${TARGET_ZIP}" -u "${DEPLOY_CREDENTIALS}" "${TARGET_URL}"

echo "Done!"