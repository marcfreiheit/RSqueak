#!/bin/bash
set -e

UNAME=linux
EX=
#set EX to sudo if required.

exitcode=0
plugins=""
plugins_suffix=""
if [[ -n "$PLUGINS" ]]; then
  plugins="--plugins=${PLUGINS}"
  plugins_suffix="-${PLUGINS}"
fi

if [ "$TRAVIS_BRANCH" == "master" ]; then
    JITTESTS_FAIL=false
else
    JITTESTS_FAIL=true
fi

case "$BUILD_ARCH" in
  32bit)
    pypy .build/build.py --batch --32bit -- $plugins
    exitcode=$?
    cp rsqueak rsqueak-x86-${UNAME}$plugins_suffix-jit-$TRAVIS_COMMIT || true
    pypy .build/jittests.py --32bit || $JITTESTS_FAIL
    $EX rm -rf .build/pypy/rpython/_cache
    ;;
  64bit)
    pypy .build/build.py --batch --64bit -- $plugins
    exitcode=$?
    cp rsqueak rsqueak-x86_64-${UNAME}$plugins_suffix-jit-$TRAVIS_COMMIT || true
    pypy .build/jittests.py --64bit || $JITTESTS_FAIL
    $EX rm -rf .build/pypy/rpython/_cache
    ;;
  lldebug)
    pypy .build/build.py --lldebug -Ojit
    exitcode=$?
    cp rsqueak rsqueak-x86-${UNAME}-dbg-$TRAVIS_COMMIT || true
    $EX rm -rf .build/pypy/rpython/_cache
    ;;
  arm*)
    armv="${BUILD_ARCH}raspbian"
    export SB2OPT="-t ${SB2NAME}"
    export CFLAGS="-march=$BUILD_ARCH -mfpu=vfp -mfloat-abi=hard -marm\
           -I${SB2}/usr/include/arm-linux-gnueabihf/"
    export LDFLAGS="-L${SB2}/usr/lib/arm-linux-gnueabihf/pulseaudio\
           -Wl,-rpath=${SB2}/usr/lib/arm-linux-gnueabihf/pulseaudio\
           -L${SB2}/usr/lib/arm-linux-gnueabihf/\
           -Wl,-rpath=${SB2}/usr/lib/arm-linux-gnueabihf/\
           -L${SB2}/lib/arm-linux-gnueabihf/\
           -Wl,-rpath=${SB2}/lib/arm-linux-gnueabihf/"
    # uses the 32-bit pypy from download_dependencies.py
    .build/pypy-linux32/bin/pypy .build/build.py --gc=incminimark --gcrootfinder=shadowstack --jit-backend=arm -Ojit --platform=arm || true
    # sometimes the translation fails because "make got killed", make sure
    oldpwd=$(pwd)
    cd /tmp/usession-default-0/testing_1/
    sb2 -t rasp make -j 5
    exitcode=$?
    cp rsqueak $oldpwd/rsqueak
    cd $oldpwd
    cp rsqueak rsqueak-$armv-${UNAME}$plugins_suffix-jit-$TRAVIS_COMMIT
    ;;
esac

exit $exitcode
