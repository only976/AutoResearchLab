/**
 * MAARS 全局状态 - 集中管理，各模块通过 window.MAARS.state 读写。
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    window.MAARS.state = {
        socket: null,
        taskOutputs: {},
        outputUserScrolled: false,
        outputBlockUserScrolled: {},
        outputLastUpdatedKey: '',
        executionLayout: null,
        chainCache: [],
        previousTaskStates: new Map(),
        thinkingThinkingBlocks: [],
        thinkingThinkingUserScrolled: false,
        thinkingThinkingBlockUserScrolled: {},
        thinkingLastUpdatedBlockKey: '',
        thinkingScheduleCounter: 0,
        thinkingPlanCounter: 0,
        thinkingPlanStreamingKey: '',
        thinkingIdeaCounter: 0,
        thinkingIdeaStreamingKey: '',
    };
})();
