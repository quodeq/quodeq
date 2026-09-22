/**
 * Shared repository API client — read-only mirrors of the project read endpoints,
 * plus config management (connect, disconnect, refresh, status) and publish/pull.
 *
 * This module is a barrel: the actual implementations live in domain
 * modules (sharedStatus.js, sharedProjectData.js, sharedPublish.js),
 * re-exported here for backward compatibility so every existing
 * `from './shared.js'` import keeps working unchanged.
 */

export * from './sharedStatus.js';
export * from './sharedProjectData.js';
export * from './sharedPublish.js';
