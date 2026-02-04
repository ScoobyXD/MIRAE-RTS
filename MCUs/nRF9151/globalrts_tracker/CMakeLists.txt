#
# GlobalRTS Tracker - nRF9151 Firmware
# Sends GNSS telemetry to GlobalRTS server and receives commands
#

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(globalrts_tracker)

target_sources(app PRIVATE
    src/main.c
)
