"""Whitelist for tools/check_dead_code.py (vulture).

Vulture sees only static references, so a name reached dynamically looks
unused. Naming it here counts as a reference and the report goes away.

Entries are allowed ONLY for names that really are reached dynamically --
Flask routes, PyObjC selectors, parser and library hooks, Protocol methods,
enum members decoded from a stored string, dataclass/TypedDict fields that
travel as dict keys, and seams whose only caller is a test. A name that is
simply dead is deleted instead; a name a grep still finds is not dead.

Names are attribute lookups on a dummy object rather than bare names so the
file stays clean under F821. Vulture records an attribute the same way it
records a name, so either spelling suppresses the report.
"""


class _Dyn:
    """Dummy carrier: every attribute read below marks that name as used."""


_ = _Dyn()

# Flask view functions. The route decorator registers them; nothing calls the name.
_._add_security_headers  # api/security.py: Flask view function; the route decorator is its only caller.
_._gzip_large_json  # api/_compression.py: Flask view function; the route decorator is its only caller.
_._handle_project_not_found  # api/routes_findings.py: Flask view function; the route decorator is its only caller.
_._security_checks  # api/security.py: Flask view function; the route decorator is its only caller.
_.ai_clients  # api/routes_discovery.py: Flask view function; the route decorator is its only caller.
_.apply_assistant_action  # api/assistant_action_routes.py: Flask view function; the route decorator is its only caller.
_.assistant_events  # api/assistant_turn_routes.py: Flask view function; the route decorator is its only caller.
_.assistant_workspace_apply  # api/assistant_workspace_routes.py: Flask view function; the route decorator is its only caller.
_.assistant_workspace_diff  # api/assistant_workspace_routes.py: Flask view function; the route decorator is its only caller.
_.assistant_workspace_discard  # api/assistant_workspace_routes.py: Flask view function; the route decorator is its only caller.
_.assistant_workspace_pr  # api/assistant_workspace_routes.py: Flask view function; the route decorator is its only caller.
_.assistant_workspace_status  # api/assistant_workspace_routes.py: Flask view function; the route decorator is its only caller.
_.browse  # api/routes_discovery.py: Flask view function; the route decorator is its only caller.
_.cancel_or_delete_evaluation  # api/routes_evaluations_item.py: Flask view function; the route decorator is its only caller.
_.client_cmd_path_check  # api/routes_discovery.py: Flask view function; the route decorator is its only caller.
_.client_models  # api/routes_discovery.py: Flask view function; the route decorator is its only caller.
_.create_assistant_session  # api/assistant_session_routes.py: Flask view function; the route decorator is its only caller.
_.delete_all  # api/routes_findings.py: Flask view function; the route decorator is its only caller.
_.delete_grade_formula  # api/_grade_formula_routes.py: Flask view function; the route decorator is its only caller.
_.dimension_eval  # api/routes_project_data.py: Flask view function; the route decorator is its only caller.
_.export_project  # api/routes_project_list.py: Flask view function; the route decorator is its only caller.
_.get_active_evaluation  # api/routes_evaluations_list.py: Flask view function; the route decorator is its only caller.
_.get_assistant_catalog  # api/assistant_session_routes.py: Flask view function; the route decorator is its only caller.
_.get_evaluation  # api/routes_evaluations_item.py: Flask view function; the route decorator is its only caller.
_.get_evaluation_progress  # api/routes_evaluations_item.py: Flask view function; the route decorator is its only caller.
_.get_grade_formula  # api/_grade_formula_routes.py: Flask view function; the route decorator is its only caller.
_.get_logs  # api/_log_routes.py: Flask view function; the route decorator is its only caller.
_.get_standards_overrides  # api/standards_overrides_routes.py: Flask view function; the route decorator is its only caller.
_.get_standards_visibility  # api/standards_visibility_routes.py: Flask view function; the route decorator is its only caller.
_.health  # api/app.py: Flask view function; the route decorator is its only caller.
_.import_from_library  # api/standards_import_routes.py: Flask view function; the route decorator is its only caller.
_.import_project_route  # api/routes_project_list.py: Flask view function; the route decorator is its only caller.
_.list_cwes  # api/standards_read_routes.py: Flask view function; the route decorator is its only caller.
_.list_dismissed  # api/routes_findings.py: Flask view function; the route decorator is its only caller.
_.list_library  # api/standards_read_routes.py: Flask view function; the route decorator is its only caller.
_.list_verified  # api/routes_findings.py: Flask view function; the route decorator is its only caller.
_.llamacpp_logs_available  # api/_llamacpp_log_routes.py: Flask view function; the route decorator is its only caller.
_.logs_css  # api/_log_routes.py: Flask view function; the route decorator is its only caller.
_.logs_js  # api/_log_routes.py: Flask view function; the route decorator is its only caller.
_.logs_page  # api/_log_routes.py: Flask view function; the route decorator is its only caller.
_.menubar_set  # api/routes_menubar.py: Flask view function; the route decorator is its only caller.
_.menubar_status  # api/routes_menubar.py: Flask view function; the route decorator is its only caller.
_.plain_logs  # api/_log_stream_routes.py: Flask view function; the route decorator is its only caller.
_.post_assistant_message  # api/assistant_turn_routes.py: Flask view function; the route decorator is its only caller.
_.preview_grade_formula  # api/_grade_formula_routes.py: Flask view function; the route decorator is its only caller.
_.project_compare_summary  # api/routes_compare.py: Flask view function; the route decorator is its only caller.
_.project_info  # api/routes_project_list.py: Flask view function; the route decorator is its only caller.
_.project_run_scores  # api/_scores_routes.py: Flask view function; the route decorator is its only caller.
_.project_runs  # api/routes_runs.py: Flask view function; the route decorator is its only caller.
_.project_scores  # api/_scores_routes.py: Flask view function; the route decorator is its only caller.
_.put_grade_formula  # api/_grade_formula_routes.py: Flask view function; the route decorator is its only caller.
_.put_standards_overrides  # api/standards_overrides_routes.py: Flask view function; the route decorator is its only caller.
_.put_standards_visibility  # api/standards_visibility_routes.py: Flask view function; the route decorator is its only caller.
_.rebuild_index_endpoint  # api/_index_routes.py: Flask view function; the route decorator is its only caller.
_.reject_assistant_action  # api/assistant_action_routes.py: Flask view function; the route decorator is its only caller.
_.restore_all  # api/routes_findings.py: Flask view function; the route decorator is its only caller.
_.run_violations  # api/routes_project_data.py: Flask view function; the route decorator is its only caller.
_.serve_root  # api/helpers.py: Flask view function; the route decorator is its only caller.
_.serve_static_or_spa  # api/helpers.py: Flask view function; the route decorator is its only caller.
_.shared_projects  # api/routes_shared_mirrors.py: Flask view function; the route decorator is its only caller.
_.shared_publish_start  # api/routes_shared_config.py: Flask view function; the route decorator is its only caller.
_.shared_refresh  # api/routes_shared_config.py: Flask view function; the route decorator is its only caller.
_.stop_assistant_turn  # api/assistant_turn_routes.py: Flask view function; the route decorator is its only caller.
_.stream_llamacpp_logs  # api/_llamacpp_log_routes.py: Flask view function; the route decorator is its only caller.
_.stream_logs  # api/_log_stream_routes.py: Flask view function; the route decorator is its only caller.
_.stream_ollama_logs  # api/_ollama_log_routes.py: Flask view function; the route decorator is its only caller.
_.stream_run_events  # api/_run_events_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_kill  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_open  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_resolve  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_session_create  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_session_kill  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_sessions  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.terminal_status  # api/terminal_routes.py: Flask view function; the route decorator is its only caller. Was masked by an unrelated same-named local var in data/fs/report_parser/runs.py._run_status_for_entry, removed by the 2026-09-22 run-list-vocabulary-into-RunState migration.
_.terminal_ws  # api/terminal_routes.py: Flask view function; the route decorator is its only caller.
_.unverify  # api/routes_findings.py: Flask view function; the route decorator is its only caller.
_.update_check  # api/routes_update.py: Flask view function; the route decorator is its only caller.
_.update_dismiss  # api/routes_update.py: Flask view function; the route decorator is its only caller.
_.update_selfupdate  # api/routes_update.py: Flask view function; the route decorator is its only caller.
_.update_settings  # api/routes_update.py: Flask view function; the route decorator is its only caller.
_.update_status  # api/routes_update.py: Flask view function; the route decorator is its only caller.

# Dataclass and TypedDict fields. The value travels as a dict key or a keyword argument, which vulture does not resolve.
_.JudgmentPayload  # core/events/models.py: Judgment field; read by name through serialization or a dict key (89 refs).
_.PERSISTED_MARKERS  # core/finding_markers.py: FindingMarker field; read by name through serialization or a dict key (4 refs).
_.accumulatedDimensionsCount  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (5 refs).
_.accumulated_dimensions_count  # core/types/dashboard.py: TrendPoint field; read by name through serialization or a dict key (1 refs).
_.active_agents  # services/_scan_progress_types.py: _DimProgress field; read by name through serialization or a dict key (2 refs).
_.analyzed  # analysis/subagents/_consolidated.py: _ConsolidatedRunContext field; read by name through serialization or a dict key (82 refs).
_.analyzed_files  # core/types/project.py: ProjectEntry field; read by name through serialization or a dict key (3 refs).
_.base_args  # assistant/adapters/cli_config.py: CliChatConfig field; read by name through serialization or a dict key (14 refs).
_.base_grade  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (5 refs).
_.base_score  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (6 refs).
_.cache_format_version  # data/cache_store/entry.py: CacheEntry field; read by name through serialization or a dict key (8 refs).
_.cache_hit  # analysis/cache/runner.py: UnitResult field; read by name through serialization or a dict key (14 refs).
_.compliance_percentage  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (18 refs).
_.confidence_interval  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (7 refs).
_.confidence_reason  # core/types/scoring.py: OverallScore field; read by name through serialization or a dict key (5 refs).
_.critical_cap  # core/types/scoring.py: Deductions field; read by name through serialization or a dict key (1 refs).
_.critical_type_count  # core/types/scoring.py: Deductions field; read by name through serialization or a dict key (9 refs).
_.dampening_multiplier  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (5 refs).
_.dateISO  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (212 refs).
_.dateLabel  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (239 refs).
_.deductions  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (21 refs).
_.dimensionDetails  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (70 refs).
_.dimensionsCount  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (41 refs).
_.estimate_reason  # services/_scan_progress_types.py: _DimProgress field; read by name through serialization or a dict key (3 refs).
_.evaluator_hash  # analysis/cache/runner.py: WorkUnit field; read by name through serialization or a dict key (3 refs).
_.evidence_date  # core/types/dimension.py: DimensionResult field; read by name through serialization or a dict key (2 refs).
_.excludes  # analysis/_dimensions.py: DimensionsConfig field; read by name through serialization or a dict key (34 refs).
_.files_cached  # services/_scan_progress_types.py: _DimProgress field; read by name through serialization or a dict key (8 refs).
_.files_excluded  # services/_scan_progress_types.py: _DimProgress field; read by name through serialization or a dict key (1 refs).
_.files_project_total  # services/_scan_progress_types.py: _DimProgress field; read by name through serialization or a dict key (8 refs).
_.grade_stability  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (10 refs).
_.heartbeat_at  # data/sqlite/run_index.py: RunRow field; read by name through serialization or a dict key (11 refs).
_.iso_25010  # analysis/_dimensions.py: DimensionEntry field; read by name through serialization or a dict key (31 refs).
_.latest_date  # core/types/project.py: ProjectEntry field; read by name through serialization or a dict key (4 refs).
_.latest_run_id  # core/types/project.py: ProjectEntry field; read by name through serialization or a dict key (10 refs).
_.major_cap  # core/types/scoring.py: Deductions field; read by name through serialization or a dict key (2 refs).
_.major_type_count  # core/types/scoring.py: Deductions field; read by name through serialization or a dict key (3 refs).
_.managed  # core/types/standard.py: StandardMeta field; read by name through serialization or a dict key (79 refs).
_.minor_type_count  # core/types/scoring.py: Deductions field; read by name through serialization or a dict key (1 refs).
_.needs_id_parse  # assistant/adapters/_cli_command.py: CliTurnSpec field; read by name through serialization or a dict key (3 refs).
_.numericAverage  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (181 refs).
_.onboarding_completed_at  # core/types/project.py: ProjectEntry field; read by name through serialization or a dict key (8 refs).
_.origin_hash  # core/types/standard.py: StandardMeta field; read by name through serialization or a dict key (10 refs).
_.overallGrade  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (323 refs).
_.path_exists  # core/types/project.py: ProjectEntry field; read by name through serialization or a dict key (3 refs).
_.previous_run_id  # core/types/dimension.py: DimensionResult field; read by name through serialization or a dict key (7 refs).
_.principle_count  # core/types/standard.py: StandardMeta field; read by name through serialization or a dict key (7 refs).
_.requirement_count  # core/types/standard.py: StandardMeta field; read by name through serialization or a dict key (7 refs).
_.runId  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (704 refs).
_.runNumericAverage  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (9 refs).
_.runOverallGrade  # services/dashboard_trend.py: TrendEntry field; read by name through serialization or a dict key (7 refs).
_.run_date_iso  # services/scoring_view/_models.py: DimResolution field; read by name through serialization or a dict key (1 refs).
_.run_state  # services/scoring_view/_models.py: DimResolution field; read by name through serialization or a dict key (4 refs).
_.runs_count  # core/types/project.py: ProjectEntry field; read by name through serialization or a dict key (10 refs).
_.sample  # core/finding_markers.py: FindingMarker field; read by name through serialization or a dict key (35 refs).
_.severity_drops  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (5 refs).
_.supports_tools  # assistant/adapters/cli_config.py: CliChatConfig field; read by name through serialization or a dict key (15 refs).
_.taxonomy_used  # core/types/scoring.py: PrincipleScore field; read by name through serialization or a dict key (8 refs).
_.total_deduction  # core/types/scoring.py: Deductions field; read by name through serialization or a dict key (1 refs).
_.untracked_files  # core/types/scan.py: ScanData field; read by name through serialization or a dict key (9 refs).
_.updated_at  # data/sqlite/run_index.py: RunRow field; read by name through serialization or a dict key (33 refs).
_.violations_per100_files  # core/types/finding.py: Totals field; read by name through serialization or a dict key (19 refs).

# Seams whose only caller lives in tests/, which this scan does not cover (src/quodeq is the scanned tree).
_.RESUME_STYLE_EXEC  # assistant/adapters/cli_config.py: Referenced only from tests/, which this scan does not cover (2 refs).
_._build_agent_config  # analysis/subagents/pool.py: Referenced only from tests/, which this scan does not cover (2 refs).
_._make_rescoring_fetcher  # services/scoring/__init__.py: Referenced only from tests/, which this scan does not cover (1 refs).
_._make_status_aware_fetcher  # services/dashboard.py: Referenced only from tests/, which this scan does not cover (9 refs).
_._reset_for_tests  # update/selfupdate.py: Referenced only from tests/, which this scan does not cover (2 refs).
_.check_node  # shared/prereqs.py: Referenced only from tests/, which this scan does not cover (4 refs).
_.check_npm  # shared/prereqs.py: Referenced only from tests/, which this scan does not cover (4 refs).
_.choose_highest_priority  # config/_discipline_detection.py: Referenced only from tests/, which this scan does not cover (1 refs).
_.clear_cached_queues  # analysis/subagents/_pool_scaling.py: Referenced only from tests/, which this scan does not cover (1 refs).
_.clear_grades  # data/sqlite/state_store.py: Referenced only from tests/, which this scan does not cover (1 refs).
_.confidence_label  # core/scoring/engine.py: Referenced only from tests/, which this scan does not cover (7 refs).
_.get_current_provider  # config/ai_provider.py: Referenced only from tests/, which this scan does not cover (6 refs).
_.get_latest_timestamp  # data/events/reader.py: Referenced only from tests/, which this scan does not cover (5 refs).
_.get_valid_categories  # config/disciplines.py: Referenced only from tests/, which this scan does not cover (4 refs).
_.grade_for_score  # core/scoring/engine.py: Referenced only from tests/, which this scan does not cover (6 refs).
_.is_subpath  # shared/paths.py: Referenced only from tests/, which this scan does not cover (3 refs).
_.is_turn_claimed  # api/assistant_turn_state.py: Referenced only from tests/, which this scan does not cover (6 refs).
_.is_violation  # core/events/models.py: Referenced only from tests/, which this scan does not cover (1 refs).
_.line_keys  # core/dismissals.py: Referenced only from tests/, which this scan does not cover (12 refs).
_.load_asvs_l1  # data/fs/standards_loader.py: Referenced only from tests/, which this scan does not cover (3 refs).
_.load_cisq  # data/fs/standards_loader.py: Referenced only from tests/, which this scan does not cover (4 refs).
_.load_compiled_refs_multi  # data/fs/standards_loader.py: Referenced only from tests/, which this scan does not cover (5 refs).
_.load_compiled_requirements_multi  # data/fs/standards_loader.py: Referenced only from tests/, which this scan does not cover (6 refs).
_.load_dimension  # data/fs/standards_loader.py: Referenced only from tests/, which this scan does not cover (4 refs).
_.read_all  # data/events/reader.py: Referenced only from tests/, which this scan does not cover (5 refs).
_.read_dismissed_snippets  # data/sqlite/findings_queries.py: Referenced only from tests/, which this scan does not cover (6 refs).
_.record_dimension_score  # data/sqlite/state_store.py: Referenced only from tests/, which this scan does not cover (12 refs).
_.record_principle_grade  # data/sqlite/state_store.py: Referenced only from tests/, which this scan does not cover (4 refs).
_.reset_for_tests  # services/warmup.py: Referenced only from tests/, which this scan does not cover (3 refs).
_.reset_hash_caches  # analysis/fingerprint.py: Referenced only from tests/, which this scan does not cover (2 refs).
_.reset_provider_config_cache  # analysis/provider_cache.py: Referenced only from tests/, which this scan does not cover (3 refs).
_.store_api_key_secure  # config/ai_provider.py: Referenced only from tests/, which this scan does not cover (21 refs).
_.tb  # shared/run_log.py: Referenced only from tests/, which this scan does not cover (2 refs).
_.tool_uses  # assistant/adapters/_stream.py: Referenced only from tests/, which this scan does not cover (6 refs).
_.update_verdict  # data/sqlite/state_store.py: Referenced only from tests/, which this scan does not cover (12 refs).
_.wait_for_trip  # analysis/cache/failure_streak.py: Referenced only from tests/, which this scan does not cover (3 refs).

# Names reached through a library, a Protocol annotation or a re-export rather than a direct call.
_.StandardReference  # core/types/standard.py: Referenced as a name or key elsewhere (4 refs outside the definition).
_._CacheEraser  # services/_run_discard.py: structural Protocol used as an annotation and as the test injection seam.
_._api_pid  # dashboard/_webview_window.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._build_workdir  # dashboard/_build_npm.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._coerce_unknown_severity  # analysis/_api_schema.py: pydantic field_validator; pydantic calls it by registration, not by name.
_._color  # shared/_log_format.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._count_eval_files  # services/cache.py: Referenced as a name or key elsewhere (8 refs outside the definition).
_._deepest_scope  # analysis/manifest_build_scope.py: Referenced as a name or key elsewhere (4 refs outside the definition).
_._dev_build_workdir  # dashboard/_build_npm.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._drain_pre_marker_buffer  # services/_job_monitor_mixin.py: Referenced as a name or key elsewhere (5 refs outside the definition).
_._get_ui_source_dir  # dashboard/_build_npm.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._poll  # menubar/app.py: Referenced as a name or key elsewhere (2 refs outside the definition).
_._read_deadline_from_status  # services/_run_status_readers.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._read_dimensions_from_status  # services/_run_status_readers.py: Referenced as a name or key elsewhere (7 refs outside the definition).
_._read_provider_model_from_status  # services/_run_status_readers.py: Referenced as a name or key elsewhere (1 refs outside the definition).
_._read_scan_summary  # services/_fs_project_primitives.py: Referenced as a name or key elsewhere (9 refs outside the definition).
_._read_time_limit_from_status  # services/_run_status_readers.py: Referenced as a name or key elsewhere (7 refs outside the definition).
_._tee_run_log  # services/_job_monitor_mixin.py: Referenced as a name or key elsewhere (5 refs outside the definition).
_.clear_accumulated_process_cache  # services/_accumulated_cache.py: Referenced as a name or key elsewhere (8 refs outside the definition).
_.close_all_for_tests  # data/cache_store/index.py: Referenced as a name or key elsewhere (4 refs outside the definition).
_.closing  # dashboard/_webview_window.py: pywebview Window event slot; the library fires it.
_.configure_provider_noninteractive  # config/ai_provider.py: Referenced as a name or key elsewhere (9 refs outside the definition).
_.count_jsonl_lines  # data/fs/stream_files.py: Referenced as a name or key elsewhere (6 refs outside the definition).
_.fetch_asvs_l1  # config/standards_fetcher.py: Referenced as a name or key elsewhere (13 refs outside the definition).
_.fetch_url  # config/_fetch_client.py: Referenced as a name or key elsewhere (17 refs outside the definition).
_.gc_stale_worktrees  # assistant/_worktree_gc.py: Referenced as a name or key elsewhere (3 refs outside the definition).
_.insert_finding  # data/sqlite/findings_repository.py: Referenced as a name or key elsewhere (38 refs outside the definition).
_.judgment_to_finding  # core/finding_mappings.py: Referenced as a name or key elsewhere (15 refs outside the definition).
_.list_by_dimension  # data/sqlite/findings_repository.py: Referenced as a name or key elsewhere (27 refs outside the definition).
_.load_taxonomy  # data/fs/standards_loader.py: Referenced as a name or key elsewhere (7 refs outside the definition).
_.menu  # menubar/app.py: rumps.App menu slot; rumps reads it to build the status item.
_.on_top  # dashboard/_webview_window_native_ops.py: pywebview Window attribute; the library applies it to the native window.
_.open_sse_streams  # api/assistant_turn_state.py: Referenced as a name or key elsewhere (5 refs outside the definition).
_.read_cached_rows  # data/sqlite/score_cache_store.py: Referenced as a name or key elsewhere (8 refs outside the definition).
_.read_run_score_from_dim_scores  # data/sqlite/state_store.py: Referenced as a name or key elsewhere (7 refs outside the definition).
_.reset_dimensions_cache  # services/_filesystem_helpers.py: Referenced as a name or key elsewhere (2 refs outside the definition).
_.save_file  # dashboard/_webview_window.py: pywebview JS API method; the frontend calls it as window.pywebview.api.save_file.
_.send_reload  # dashboard/_instance.py: Referenced as a name or key elsewhere (8 refs outside the definition).
_.sender  # dashboard/: ObjC selector argument; AppKit passes it positionally.
_.set_fetch_client  # config/_fetch_client.py: Referenced as a name or key elsewhere (2 refs outside the definition).
_.set_titlebar_theme  # dashboard/_webview_window.py: pywebview JS API method; the frontend calls it on pywebviewready.
_.set_verdict  # data/sqlite/findings_repository.py: Referenced as a name or key elsewhere (4 refs outside the definition).
_.sync_source_to_workdir  # dashboard/_build_npm.py: Referenced as a name or key elsewhere (7 refs outside the definition).

# Public re-export aliases. Importers name them; nothing in-package reads them.
_.ENV_MAX_DURATION  # _cli_env.py: Public re-export alias; importers name it, nothing in-package reads it.
_.ENV_MAX_TURNS  # _cli_env.py: Public re-export alias; importers name it, nothing in-package reads it.
_.ENV_NO_CONSOLIDATE  # _cli_env.py: Public re-export alias kept for symmetry with the three siblings cli.py imports.
_.ENV_POOL_BUDGET  # _cli_env.py: Public re-export alias; importers name it, nothing in-package reads it.
_.cli_env_int  # _cli_env.py: Public re-export alias; importers name it, nothing in-package reads it.
_.cli_environ  # _cli_env.py: Public re-export alias; importers name it, nothing in-package reads it.
_.run_pipeline_with_cleanup  # cli_evaluation.py: Public re-export alias; importers name it, nothing in-package reads it.
_.setup_run_dirs  # cli_evaluation.py: Public re-export alias; importers name it, nothing in-package reads it.

# Enum members decoded from the string value stored in events.jsonl or a manifest.
_.DIMENSION_COMPLETED  # core/events/models.py: EventType member; decoded from its stored string value.
_.DIMENSION_FAILED  # core/events/models.py: EventType member; decoded from its stored string value.
_.EMBEDDED  # context/_project_shape_types.py: Deployment member; decoded from its stored string value.
_.RUN_ABORTED  # core/events/models.py: EventType member; decoded from its stored string value.
_.RUN_COMPLETED  # core/events/models.py: EventType member; decoded from its stored string value.
_.RUN_STARTED  # core/events/models.py: EventType member; decoded from its stored string value.
_.get_model_for_tier  # config/ai_models.py: ModelTier member; decoded from its stored string value.
_.FAILURE_STREAK  # core/run/exit_reason.py: ExitReason member; decoded from its stored string value.
_.STALE_DETECTED  # core/run/exit_reason.py: ExitReason member; decoded from its stored string value.
_.STALE_LEGACY_NO_PID  # core/run/exit_reason.py: ExitReason member; decoded from its stored string value.
_.STALE_LEGACY_PID_DEAD  # core/run/exit_reason.py: ExitReason member; decoded from its stored string value.

# Closed-vocabulary seams. Each names one home module's derived set or
# parser; the readers still compare bare strings, so today the tests in
# tests/core are the only static callers. Delete an entry as its readers
# move onto it.
_.ACTIVE_STATES  # core/run/state.py: RunState subset; tests/core/run/test_state_parse.py is its only caller.
_.DEADLINE_EXIT_REASONS  # core/run/exit_reason.py: ExitReason subset; tests/core/run/test_exit_reason.py is its only caller.
_.JOB_TERMINAL  # core/run/job_status.py: JobStatus subset; tests/core/run/test_job_status.py is its only caller.
_.SEVERITY_ORDER  # core/types/severity.py: Severity ordering; tests/core/types/test_severity.py is its only caller.
_.parse_run_state  # core/run/state.py: legacy-spelling parser; tests/core/run/test_state_parse.py is its only caller.
_.parse_severity  # core/types/severity.py: lenient severity parser; tests/core/types/test_severity.py is its only caller.
_.strip_external_prefix  # core/run/job_status.py: external job id helper; tests/core/run/test_job_status.py is its only caller.

# PyObjC selectors. AppKit dispatches them by the selector string, never by the Python name.
_.didExitFullScreen_  # dashboard/_webview_window_fullscreen.py: PyObjC selector on None; AppKit dispatches it by name.
_.openHelp_  # dashboard/_webview_window_help_menu.py: PyObjC selector on None; AppKit dispatches it by name.
_.scheduleTimer_  # dashboard/_webview_window_help_menu.py: PyObjC selector on None; AppKit dispatches it by name.
_.showAbout_  # dashboard/_webview_window_about.py: PyObjC selector on _MacAppState; AppKit dispatches it by name.
_.tryInstall_  # dashboard/_webview_window_about.py: PyObjC selector on _MacAppState; AppKit dispatches it by name.
_.willEnterFullScreen_  # dashboard/_webview_window_fullscreen.py: PyObjC selector on None; AppKit dispatches it by name.

# html.parser.HTMLParser hooks. The base parser calls them.
_.handle_data  # assistant/tools/_web_tools.py: HTMLParser hook on _DdgResultParser; the base parser calls it.
_.handle_endtag  # assistant/tools/_web_tools.py: HTMLParser hook on _DdgResultParser; the base parser calls it.
_.handle_starttag  # assistant/tools/_web_tools.py: HTMLParser hook on _DdgResultParser; the base parser calls it.

# sqlite3 connection attribute. The driver reads it; we only assign it.
_.row_factory  # data/projection/grade_projector.py: sqlite3 connection attribute; the driver reads it, we only assign it.

# Port methods. Adapters implement them and callers go through the port.
_.insert_finding  # data/ports/findings.py: FindingsRepository port method; adapters implement it and callers go through the port.
_.list_by_dimension  # data/ports/findings.py: FindingsRepository port method; adapters implement it and callers go through the port.
_.read_run_score_from_dim_scores  # data/ports/grade_tables.py: GradeTablesReader port method; adapters implement it and callers go through the port.
_.set_verdict  # data/ports/findings.py: FindingsRepository port method; adapters implement it and callers go through the port.
