# Install script for directory: C:/ncs/v3.2.1/zephyr

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "C:/Program Files (x86)/Zephyr-Kernel")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "C:/ncs/toolchains/66cdf9b75e/opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-objdump.exe")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/arch/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/lib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/soc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/boards/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/subsys/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/drivers/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/nrf/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/hostap/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/mcuboot/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/mbedtls/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/trusted-firmware-m/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/cjson/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/azure-sdk-for-c/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/cirrus-logic/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/openthread/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/memfault-firmware-sdk/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/canopennode/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/chre/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/lz4/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/zscilib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/cmsis/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/cmsis-dsp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/cmsis-nn/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/cmsis_6/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/fatfs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/hal_nordic/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/hal_st/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/hal_tdk/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/hal_wurthelektronik/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/liblc3/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/libmetal/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/littlefs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/loramac-node/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/lvgl/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/mipi-sys-t/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/nanopb/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/nrf_wifi/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/open-amp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/percepio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/picolibc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/segger/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/uoscore-uedhoc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/zcbor/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/nrfxlib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/nrf_hw_models/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/modules/connectedhomeip/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/kernel/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/cmake/flash/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/cmake/usage/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/Users/Jonat/MIRAERTS/MCUs/nRF9151/globalrts_tracker/build/globalrts_tracker/zephyr/cmake/reports/cmake_install.cmake")
endif()

