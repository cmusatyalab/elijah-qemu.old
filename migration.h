/*
 * QEMU live migration
 *
 * Copyright IBM, Corp. 2008
 *
 * Authors:
 *  Anthony Liguori   <aliguori@us.ibm.com>
 *
 * This work is licensed under the terms of the GNU GPL, version 2.  See
 * the COPYING file in the top-level directory.
 *
 */

#ifndef QEMU_MIGRATION_H
#define QEMU_MIGRATION_H

#include "qdict.h"
#include "qemu-common.h"
#include "notify.h"
#include "error.h"
#include "qemu-thread.h"

typedef struct MigrationState MigrationState;

struct MigrationState
{
    int64_t bandwidth_limit;
    QEMUFile *file;
    int fd;
    int state;
    int (*get_error)(MigrationState *s);
    int (*close)(MigrationState *s);
    int (*write)(MigrationState *s, const void *buff, size_t size);
    void *opaque;
    int blk;
    int shared;
    QemuThread raw_thread;
    QemuMutex serial_lock;
    bool ongoing;  /* protected by serial_lock */
};

typedef enum {
    RAW_NONE = 0,
    RAW_SUSPEND,
    RAW_LIVE
} raw_type;

void process_incoming_migration(QEMUFile *f);

int qemu_start_incoming_migration(const char *uri, Error **errp);

uint64_t migrate_max_downtime(void);

void do_info_migrate_print(Monitor *mon, const QObject *data);

void do_info_migrate(Monitor *mon, QObject **ret_data);

int exec_start_incoming_migration(const char *host_port);

int exec_start_outgoing_migration(MigrationState *s, const char *host_port);

int tcp_start_incoming_migration(const char *host_port, Error **errp);

int tcp_start_outgoing_migration(MigrationState *s, const char *host_port,
                                 Error **errp);

int unix_start_incoming_migration(const char *path);

int unix_start_outgoing_migration(MigrationState *s, const char *path);

int fd_start_incoming_migration(const char *path);

int raw_start_incoming_migration(const char *path, raw_type type);

int fd_start_outgoing_migration(MigrationState *s, const char *fdname);

int raw_start_outgoing_migration(MigrationState *s, const char *fdname, raw_type raw);

void migrate_fd_error(MigrationState *s);

void migrate_fd_connect(MigrationState *s);

void migrate_fd_connect_raw(MigrationState *s, raw_type type);

void add_migration_state_change_notifier(Notifier *notify);
void remove_migration_state_change_notifier(Notifier *notify);
bool migration_is_active(MigrationState *);
bool migration_has_finished(MigrationState *);
bool migration_has_failed(MigrationState *);

uint64_t ram_bytes_remaining(void);
uint64_t ram_bytes_transferred(void);
uint64_t ram_bytes_total(void);

int ram_save_live(QEMUFile *f, int stage, void *opaque);
void ram_save_raw(QEMUFile *f, void *opaque);
int ram_save_raw_live(QEMUFile *f, int stage, void *opaque);
int ram_load(QEMUFile *f, void *opaque, int version_id);

/**
 * @migrate_add_blocker - prevent migration from proceeding
 *
 * @reason - an error to be returned whenever migration is attempted
 */
void migrate_add_blocker(Error *reason);

/**
 * @migrate_del_blocker - remove a blocking error from migration
 *
 * @reason - the error blocking migration
 */
void migrate_del_blocker(Error *reason);

void set_use_raw(QEMUFile *file, raw_type type);
bool use_raw_none(QEMUFile *file);
bool use_raw_suspend(QEMUFile *file);
bool use_raw_live(QEMUFile *file);

uint64_t raw_dump_device_state(bool suspend, bool print);
int qemu_savevm_dump_non_live(QEMUFile *f, bool suspend, bool print);
void qemu_fopen_ops_buffered_wrapper(MigrationState *s);
uint64_t raw_ram_total_pages(uint64_t total_device_size);
void raw_live_stop(QEMUFile *f);
void raw_live_iterate(QEMUFile *f);
void check_wait_raw_live_iterate(QEMUFile *f);
bool check_raw_live_stop(QEMUFile *f);
void clear_raw_live_iterate(QEMUFile *f);
void raw_live_randomize(void);
void raw_live_unrandomize(void);
bool check_raw_live_random(void);

void init_raw_live(void);
void clean_raw_live(void);

void init_migration_state(void);
void clean_migration_state(void);

uint64_t get_blob_pos(struct QEMUFile *f);
void set_blob_pos(QEMUFile *f, uint64_t pos);

void reset_iter_seq(struct QEMUFile *);
void inc_iter_seq(struct QEMUFile *);
uint64_t get_iter_seq(struct QEMUFile *f);

#define USE_MIGRATION_DEBUG_FILE

#ifdef USE_MIGRATION_DEBUG_FILE
extern FILE *debug_file;
#define MIGRATION_DEBUG_FILE "/tmp/qemu_debug_messages"
#endif

void debug_print_timestamp(const char *msg);
void qemu_file_enable_blob(QEMUFile *f);
bool qemu_file_blob_enabled(QEMUFile *f);
void munmap_ram_blocks(void);

#endif
