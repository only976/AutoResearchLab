/**
 * MAARS Settings - AI 模式与阶段配置（纯数据）。
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    const PHASES = [
        { key: 'idea', label: 'Idea LLM' },
        { key: 'atomicity', label: 'Atomicity Check' },
        { key: 'decompose', label: 'Decompose' },
        { key: 'format', label: 'Format' },
        { key: 'quality', label: 'Quality Assess' },
        { key: 'execute', label: 'Task Execute' },
        { key: 'validate', label: 'Task Validate' },
    ];

    const MODE_DESCRIPTIONS = {
        mock: {
            title: 'Mock LLM config',
            desc: 'Mock LLM mode: Plan and task use LLM execution path with simulated output. No API key required. Quick flow and UI testing.',
        },
        mockagent: {
            title: 'Mock Agent config',
            desc: 'Mock Agent mode: Plan uses mock; task uses Agent path with simulated tool calls (ReadArtifact, ReadFile, Finish) and output. No API key required.',
        },
        llm: {
            title: 'LLM config',
            desc: 'Plan and task execution both use LLM calls (single-turn). Plan decomposes tasks; task execution generates output once and validates. Select or create preset in Preset.',
            presetNote: true,
        },
        llmagent: {
            title: 'LLM+Agent config',
            desc: 'Plan uses LLM (single-turn atomicity/decompose/format). Task execution uses Agent mode (ReAct-style with tools): ReadArtifact, ReadFile, WriteFile, Finish, ListSkills, LoadSkill.',
            presetNote: true,
        },
        agent: {
            title: 'Agent config',
            desc: 'Plan and task execution both use Agent mode (ReAct-style with tools). Plan: CheckAtomicity, Decompose, FormatTask, AddTasks, etc. Task: ReadArtifact, ReadFile, WriteFile, Finish, ListSkills, LoadSkill.',
            presetNote: true,
        },
    };

    const MODE_PARAMS = {
        mock: [
            { key: 'executionPassProbability', label: 'Execution pass rate', type: 'number', min: 0, max: 1, step: 0.05, default: 0.95, section: 'Mock', tip: 'Random pass probability for mock execution' },
            { key: 'validationPassProbability', label: 'Validation pass rate', type: 'number', min: 0, max: 1, step: 0.05, default: 0.95, section: 'Mock', tip: 'Random pass probability for mock validation' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Mock', tip: 'Max retries after task failure' },
        ],
        mockagent: [
            { key: 'executionPassProbability', label: 'Execution pass rate', type: 'number', min: 0, max: 1, step: 0.05, default: 0.95, section: 'Mock', tip: 'Random pass probability for mock execution' },
            { key: 'validationPassProbability', label: 'Validation pass rate', type: 'number', min: 0, max: 1, step: 0.05, default: 0.95, section: 'Mock', tip: 'Random pass probability for mock validation' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Mock', tip: 'Max retries after task failure' },
        ],
        llm: [
            { key: 'ideaLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Idea LLM', tip: 'Temperature for idea LLM keyword extraction' },
            { key: 'planLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Plan LLM', tip: 'Temperature for plan LLM (atomicity/decompose/format)' },
            { key: 'taskLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Task LLM', tip: 'Temperature for task LLM output' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Task LLM', tip: 'Max retries after execution/validation failure' },
        ],
        llmagent: [
            { key: 'ideaLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Idea LLM', tip: 'Temperature for idea LLM keyword extraction' },
            { key: 'planLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Plan LLM', tip: 'Temperature for plan LLM (atomicity/decompose/format)' },
            { key: 'taskLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Task Agent', tip: 'Temperature for task Agent LLM' },
            { key: 'taskAgentMaxTurns', label: 'Max turns', type: 'number', min: 1, max: 30, default: 15, section: 'Task Agent', tip: 'Max turns for task Agent loop (incl. tool calls)' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Task Agent', tip: 'Max retries after execution/validation failure' },
        ],
        agent: [
            { key: 'planAgentMaxTurns', label: 'Max turns', type: 'number', min: 1, max: 50, default: 30, section: 'Plan Agent', tip: 'Max turns for plan Agent loop' },
            { key: 'planLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Plan Agent', tip: 'Temperature for plan Agent LLM' },
            { key: 'taskLlmTemperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Task Agent', tip: 'Temperature for task Agent LLM' },
            { key: 'taskAgentMaxTurns', label: 'Max turns', type: 'number', min: 1, max: 30, default: 15, section: 'Task Agent', tip: 'Max turns for task Agent loop (incl. tool calls)' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Task Agent', tip: 'Max retries after execution/validation failure' },
        ],
    };

    window.MAARS.settingsModeConfig = { PHASES, MODE_DESCRIPTIONS, MODE_PARAMS };
})();
