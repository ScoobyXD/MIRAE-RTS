/*
 * GlobalRTS Tracker - nRF9151 Firmware
 * 
 * Sends GNSS telemetry to GlobalRTS server via cellular and receives commands.
 * Uses HTTP (not HTTPS) for simplicity during development.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/socket.h>
#include <modem/lte_lc.h>
#include <modem/nrf_modem_lib.h>
#include <nrf_modem_at.h>
#include <nrf_modem_gnss.h>
#include <cJSON.h>

LOG_MODULE_REGISTER(globalrts_tracker, LOG_LEVEL_INF);

/* ============================================
 * Configuration
 * ============================================ */

#define ROVER_ID        "nrf9151-001"
#define ROVER_NAME      "nRF9151 Tracker"
#define SERVER_HOST     "miraeopus.com"
#define SERVER_PORT     80
#define TELEMETRY_PATH  "/api/telemetry"
#define COMMANDS_PATH   "/api/commands/" ROVER_ID

/* Intervals */
#define TELEMETRY_INTERVAL_MS   1000
#define COMMAND_POLL_INTERVAL   2

/* Buffer sizes */
#define RECV_BUF_SIZE   2048
#define SEND_BUF_SIZE   1024
#define JSON_BUF_SIZE   512

/* ============================================
 * Global State
 * ============================================ */

static struct nrf_modem_gnss_pvt_data_frame current_pvt;
static bool gnss_fix_valid = false;
static bool lte_connected = false;
static int telemetry_count = 0;

/* Buffers */
static char recv_buf[RECV_BUF_SIZE];
static char send_buf[SEND_BUF_SIZE];
static char json_buf[JSON_BUF_SIZE];

/* Semaphores */
static K_SEM_DEFINE(lte_connected_sem, 0, 1);

/* ============================================
 * LTE Event Handler
 * ============================================ */

static void lte_handler(const struct lte_lc_evt *const evt)
{
    switch (evt->type) {
    case LTE_LC_EVT_NW_REG_STATUS:
        if (evt->nw_reg_status == LTE_LC_NW_REG_REGISTERED_HOME ||
            evt->nw_reg_status == LTE_LC_NW_REG_REGISTERED_ROAMING) {
            LOG_INF("LTE connected");
            lte_connected = true;
            k_sem_give(&lte_connected_sem);
        } else {
            lte_connected = false;
        }
        break;
    case LTE_LC_EVT_PSM_UPDATE:
        LOG_INF("PSM: TAU=%d, Active=%d", evt->psm_cfg.tau, evt->psm_cfg.active_time);
        break;
    default:
        break;
    }
}

/* ============================================
 * GNSS Event Handler
 * ============================================ */

static void gnss_event_handler(int event)
{
    int err;

    switch (event) {
    case NRF_MODEM_GNSS_EVT_PVT:
        err = nrf_modem_gnss_read(&current_pvt, sizeof(current_pvt), NRF_MODEM_GNSS_DATA_PVT);
        if (err == 0) {
            if (current_pvt.flags & NRF_MODEM_GNSS_PVT_FLAG_FIX_VALID) {
                gnss_fix_valid = true;
            } else {
                gnss_fix_valid = false;
            }
        }
        break;
    default:
        break;
    }
}

/* ============================================
 * Initialize Modem
 * ============================================ */

static int modem_init(void)
{
    int err;

    LOG_INF("Initializing modem...");

    err = nrf_modem_lib_init();
    if (err) {
        LOG_ERR("Modem init failed: %d", err);
        return err;
    }

    /* Register LTE event handler */
    lte_lc_register_handler(lte_handler);

    return 0;
}

/* ============================================
 * Connect to LTE Network
 * ============================================ */

static int lte_connect_network(void)
{
    int err;

    LOG_INF("Connecting to LTE network...");

    err = lte_lc_connect_async(lte_handler);
    if (err) {
        LOG_ERR("LTE connect failed: %d", err);
        return err;
    }

    /* Wait for connection (timeout 120 seconds) */
    err = k_sem_take(&lte_connected_sem, K_SECONDS(120));
    if (err) {
        LOG_ERR("LTE connection timeout");
        return -ETIMEDOUT;
    }

    LOG_INF("LTE connected successfully");
    return 0;
}

/* ============================================
 * Initialize GNSS
 * ============================================ */

static int gnss_init(void)
{
    int err;

    LOG_INF("Initializing GNSS...");

    /* Register GNSS event handler */
    err = nrf_modem_gnss_event_handler_set(gnss_event_handler);
    if (err) {
        LOG_ERR("GNSS event handler set failed: %d", err);
        return err;
    }

    /* Set NMEA mask */
    uint16_t nmea_mask = NRF_MODEM_GNSS_NMEA_GGA_MASK |
                         NRF_MODEM_GNSS_NMEA_GLL_MASK |
                         NRF_MODEM_GNSS_NMEA_GSA_MASK |
                         NRF_MODEM_GNSS_NMEA_GSV_MASK;
    nrf_modem_gnss_nmea_mask_set(nmea_mask);

    /* Set use case: multiple hot start */
    err = nrf_modem_gnss_use_case_set(NRF_MODEM_GNSS_USE_CASE_MULTIPLE_HOT_START);
    if (err) {
        LOG_WRN("Use case set failed: %d", err);
    }

    /* Continuous tracking mode */
    err = nrf_modem_gnss_fix_interval_set(1);
    if (err) {
        LOG_ERR("Fix interval set failed: %d", err);
        return err;
    }

    /* Start GNSS */
    err = nrf_modem_gnss_start();
    if (err) {
        LOG_ERR("GNSS start failed: %d", err);
        return err;
    }

    LOG_INF("GNSS started, waiting for fix...");
    return 0;
}

/* ============================================
 * HTTP Helper - Send request and get response
 * Uses zsock_* functions for modem-offloaded sockets
 * ============================================ */

static int http_request(const char *method, const char *path, 
                        const char *body, char *response, size_t response_size)
{
    int sock;
    int err;
    int bytes;
    struct zsock_addrinfo *res = NULL;
    struct zsock_addrinfo hints = {
        .ai_family = AF_INET,
        .ai_socktype = SOCK_STREAM,
    };

    /* Resolve hostname */
    err = zsock_getaddrinfo(SERVER_HOST, "80", &hints, &res);
    if (err || res == NULL) {
        LOG_ERR("DNS failed: %d", err);
        return -1;
    }

    /* Create socket */
    sock = zsock_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0) {
        LOG_ERR("Socket failed: %d", errno);
        zsock_freeaddrinfo(res);
        return -1;
    }

    /* Connect */
    err = zsock_connect(sock, res->ai_addr, res->ai_addrlen);
    zsock_freeaddrinfo(res);
    
    if (err) {
        LOG_ERR("Connect failed: %d", errno);
        zsock_close(sock);
        return -1;
    }

    /* Build HTTP request */
    int req_len;
    if (body) {
        int content_len = strlen(body);
        req_len = snprintf(send_buf, sizeof(send_buf),
            "%s %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n"
            "\r\n"
            "%s",
            method, path, SERVER_HOST, content_len, body);
    } else {
        req_len = snprintf(send_buf, sizeof(send_buf),
            "%s %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Connection: close\r\n"
            "\r\n",
            method, path, SERVER_HOST);
    }

    /* Send request */
    bytes = zsock_send(sock, send_buf, req_len, 0);
    if (bytes != req_len) {
        LOG_ERR("Send failed: %d of %d", bytes, req_len);
        zsock_close(sock);
        return -1;
    }

    /* Receive response */
    memset(response, 0, response_size);
    int total = 0;
    while (total < response_size - 1) {
        bytes = zsock_recv(sock, response + total, response_size - 1 - total, 0);
        if (bytes <= 0) {
            break;
        }
        total += bytes;
    }

    zsock_close(sock);

    /* Check for HTTP 200 */
    if (strstr(response, "HTTP/1.1 200") == NULL && 
        strstr(response, "HTTP/1.0 200") == NULL) {
        LOG_WRN("HTTP error");
        return -1;
    }

    return total;
}

/* ============================================
 * Build Telemetry JSON
 * ============================================ */

static int build_telemetry_json(char *buf, size_t buf_size)
{
    return snprintf(buf, buf_size,
        "{"
        "\"id\":\"%s\","
        "\"name\":\"%s\","
        "\"type\":\"robot\","
        "\"lat\":%.6f,"
        "\"lon\":%.6f,"
        "\"alt\":%.1f,"
        "\"speed\":%.2f,"
        "\"heading\":%.1f,"
        "\"accuracy\":%.1f,"
        "\"altAccuracy\":%.1f,"
        "\"speedAccuracy\":%.2f,"
        "\"headingAccuracy\":%.1f,"
        "\"vSpeed\":%.2f,"
        "\"vSpeedAccuracy\":%.2f,"
        "\"pdop\":%.1f,"
        "\"hdop\":%.1f,"
        "\"vdop\":%.1f,"
        "\"tdop\":%.1f,"
        "\"battery\":100,"
        "\"status\":\"online\""
        "}",
        ROVER_ID,
        ROVER_NAME,
        current_pvt.latitude,
        current_pvt.longitude,
        (double)current_pvt.altitude,
        (double)current_pvt.speed,
        (double)current_pvt.heading,
        (double)current_pvt.accuracy,
        (double)current_pvt.altitude_accuracy,
        (double)current_pvt.speed_accuracy,
        (double)current_pvt.heading_accuracy,
        (double)current_pvt.vertical_speed,
        (double)current_pvt.vertical_speed_accuracy,
        (double)current_pvt.pdop,
        (double)current_pvt.hdop,
        (double)current_pvt.vdop,
        (double)current_pvt.tdop
    );
}

/* ============================================
 * Send Telemetry to GlobalRTS
 * ============================================ */

static int send_telemetry(void)
{
    int err;

    if (!gnss_fix_valid) {
        return -1;
    }

    /* Build JSON payload */
    build_telemetry_json(json_buf, sizeof(json_buf));

    LOG_INF("TX: %.6f, %.6f", current_pvt.latitude, current_pvt.longitude);

    /* Send POST request */
    err = http_request("POST", TELEMETRY_PATH, json_buf, recv_buf, sizeof(recv_buf));
    if (err < 0) {
        LOG_ERR("Telemetry failed");
        return err;
    }

    return 0;
}

/* ============================================
 * Poll for Commands from GlobalRTS
 * ============================================ */

static int poll_commands(void)
{
    int err;
    char *body_start;

    /* Send GET request */
    err = http_request("GET", COMMANDS_PATH, NULL, recv_buf, sizeof(recv_buf));
    if (err < 0) {
        return err;
    }

    /* Find JSON body (after \r\n\r\n) */
    body_start = strstr(recv_buf, "\r\n\r\n");
    if (!body_start) {
        return -1;
    }
    body_start += 4;

    /* Parse JSON response */
    cJSON *root = cJSON_Parse(body_start);
    if (!root) {
        return -1;
    }

    cJSON *commands = cJSON_GetObjectItem(root, "commands");
    if (!commands || !cJSON_IsArray(commands)) {
        cJSON_Delete(root);
        return 0;
    }

    int cmd_count = cJSON_GetArraySize(commands);
    if (cmd_count == 0) {
        cJSON_Delete(root);
        return 0;
    }

    /* Process each command */
    for (int i = 0; i < cmd_count; i++) {
        cJSON *cmd = cJSON_GetArrayItem(commands, i);
        if (!cmd) continue;

        cJSON *type = cJSON_GetObjectItem(cmd, "type");
        cJSON *payload = cJSON_GetObjectItem(cmd, "payload");

        if (!type || !cJSON_IsString(type)) continue;

        const char *cmd_type = type->valuestring;

        if (strcmp(cmd_type, "navigate") == 0 && payload) {
            cJSON *lat = cJSON_GetObjectItem(payload, "latitude");
            cJSON *lon = cJSON_GetObjectItem(payload, "longitude");
            
            if (lat && lon && cJSON_IsNumber(lat) && cJSON_IsNumber(lon)) {
                printk("\n");
                printk("========================================\n");
                printk("  RECEIVED COMMAND: navigate\n");
                printk("  Target: %.6f, %.6f\n", lat->valuedouble, lon->valuedouble);
                printk("========================================\n");
                printk("\n");
            }
        } else if (strcmp(cmd_type, "stop") == 0) {
            printk("\n");
            printk("========================================\n");
            printk("  RECEIVED COMMAND: stop\n");
            printk("========================================\n");
            printk("\n");
        } else {
            printk("\n");
            printk("========================================\n");
            printk("  RECEIVED COMMAND: %s\n", cmd_type);
            printk("========================================\n");
            printk("\n");
        }
    }

    cJSON_Delete(root);
    return cmd_count;
}

/* ============================================
 * Print GNSS Status
 * ============================================ */

static void print_gnss_status(void)
{
    if (gnss_fix_valid) {
        printk("\033[2J\033[H");  /* Clear screen */
        printk("=== GlobalRTS Tracker ===\n");
        printk("Lat: %.6f  Lon: %.6f\n", current_pvt.latitude, current_pvt.longitude);
        printk("Alt: %.1fm  Speed: %.2fm/s  Hdg: %.1f\n", 
               (double)current_pvt.altitude, 
               (double)current_pvt.speed,
               (double)current_pvt.heading);
        printk("Acc: %.1fm  PDOP: %.1f  HDOP: %.1f\n",
               (double)current_pvt.accuracy,
               (double)current_pvt.pdop,
               (double)current_pvt.hdop);
        printk("Telemetry #%d -> %s\n", telemetry_count, SERVER_HOST);
    } else {
        int tracked = 0;
        for (int i = 0; i < NRF_MODEM_GNSS_MAX_SATELLITES; i++) {
            if (current_pvt.sv[i].sv > 0) {
                tracked++;
            }
        }
        printk("\r[GNSS] Searching... Sats: %d    ", tracked);
    }
}

/* ============================================
 * Main Entry Point
 * ============================================ */

int main(void)
{
    int err;

    printk("\n");
    printk("==========================================\n");
    printk("  GlobalRTS Tracker - nRF9151\n");
    printk("  ID: %s\n", ROVER_ID);
    printk("  Server: %s:%d\n", SERVER_HOST, SERVER_PORT);
    printk("==========================================\n");
    printk("\n");

    /* Initialize modem */
    err = modem_init();
    if (err) {
        LOG_ERR("Modem init failed: %d", err);
        return err;
    }

    /* Connect to LTE */
    err = lte_connect_network();
    if (err) {
        LOG_ERR("LTE connect failed: %d", err);
        return err;
    }

    /* Start GNSS */
    err = gnss_init();
    if (err) {
        LOG_ERR("GNSS init failed: %d", err);
        return err;
    }

    printk("\nWaiting for GNSS fix (30-60 sec cold start)...\n\n");

    /* Main loop */
    int cycle = 0;
    while (1) {
        k_sleep(K_MSEC(TELEMETRY_INTERVAL_MS));

        print_gnss_status();

        if (gnss_fix_valid && lte_connected) {
            err = send_telemetry();
            if (err == 0) {
                telemetry_count++;
            }

            cycle++;
            if (cycle >= COMMAND_POLL_INTERVAL) {
                cycle = 0;
                poll_commands();
            }
        }
    }

    return 0;
}
