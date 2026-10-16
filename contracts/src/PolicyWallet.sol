// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Like {
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title PolicyWallet
/// @notice Holds one stablecoin on behalf of an owner and lets a separate AI agent key spend it
///         only inside owner-set limits: a per-transfer cap, a rolling 24-hour cap (hourly buckets),
///         a recipient allowlist and a pause switch. Anything outside those limits needs a one-time
///         approval signed by the owner for that exact recipient, amount and intent id.
///         Every payment emits the intent id, so each transaction hash links to the agent's audit log.
contract PolicyWallet {
    address public owner;
    address public agent;
    IERC20Like public immutable token;

    uint256 public perTransferCap;   // token base units (6 decimals for tUSDC)
    uint256 public rollingCap;       // total the agent may spend in any 24-hour window
    bool public paused;
    mapping(address => bool) public allowlist;

    struct Approval { address to; uint256 amount; bool used; }
    mapping(bytes32 => Approval) public approvals;   // keyed by intent id

    uint256[24] private bucketSpent;   // amount spent in each hourly bucket
    uint256[24] private bucketHour;    // absolute hour index the bucket currently holds

    event Payment(bytes32 indexed intentId, address indexed to, uint256 amount, address indexed by, bool viaApproval);
    event PolicyUpdated(uint256 perTransferCap, uint256 rollingCap);
    event AllowlistUpdated(address indexed to, bool allowed);
    event PausedSet(bool paused);
    event AgentUpdated(address indexed agent);
    event ApprovalGranted(bytes32 indexed intentId, address indexed to, uint256 amount);

    error NotOwner();
    error NotAgent();
    error IsPaused();
    error NotAllowlisted(address to);
    error ExceedsPerTransferCap(uint256 amount, uint256 cap);
    error ExceedsRollingCap(uint256 amount, uint256 spentLast24h, uint256 cap);
    error ApprovalMismatch();
    error ApprovalUsed();
    error TransferFailed();
    error ZeroAddress();

    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }
    modifier onlyAgent() { if (msg.sender != agent) revert NotAgent(); _; }

    constructor(address _agent, address _token, uint256 _perTransferCap, uint256 _rollingCap) {
        if (_agent == address(0) || _token == address(0)) revert ZeroAddress();
        owner = msg.sender;
        agent = _agent;
        token = IERC20Like(_token);
        perTransferCap = _perTransferCap;
        rollingCap = _rollingCap;
        emit AgentUpdated(_agent);
        emit PolicyUpdated(_perTransferCap, _rollingCap);
    }

    // ---------------------------------------------------------------- agent paths

    /// @notice Routine payment: allowlisted recipient, within both caps, not paused.
    function agentTransfer(address to, uint256 amount, bytes32 intentId) external onlyAgent {
        if (paused) revert IsPaused();
        if (!allowlist[to]) revert NotAllowlisted(to);
        if (amount > perTransferCap) revert ExceedsPerTransferCap(amount, perTransferCap);
        uint256 spent = spentLast24h();
        if (spent + amount > rollingCap) revert ExceedsRollingCap(amount, spent, rollingCap);
        _record(amount);
        _send(to, amount);
        emit Payment(intentId, to, amount, msg.sender, false);
    }

    /// @notice Exception payment: executes exactly the transfer the owner approved once, then burns the approval.
    function agentTransferWithApproval(address to, uint256 amount, bytes32 intentId) external onlyAgent {
        if (paused) revert IsPaused();
        Approval storage a = approvals[intentId];
        if (a.to == address(0) || a.to != to || a.amount != amount) revert ApprovalMismatch();
        if (a.used) revert ApprovalUsed();
        a.used = true;
        _send(to, amount);
        emit Payment(intentId, to, amount, msg.sender, true);
    }

    // ---------------------------------------------------------------- owner governance

    function approveOnce(bytes32 intentId, address to, uint256 amount) external onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        approvals[intentId] = Approval({to: to, amount: amount, used: false});
        emit ApprovalGranted(intentId, to, amount);
    }

    function setPolicy(uint256 _perTransferCap, uint256 _rollingCap) external onlyOwner {
        perTransferCap = _perTransferCap;
        rollingCap = _rollingCap;
        emit PolicyUpdated(_perTransferCap, _rollingCap);
    }

    function setAllowlist(address to, bool allowed) external onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        allowlist[to] = allowed;
        emit AllowlistUpdated(to, allowed);
    }

    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
        emit PausedSet(_paused);
    }

    function setAgent(address _agent) external onlyOwner {
        if (_agent == address(0)) revert ZeroAddress();
        agent = _agent;
        emit AgentUpdated(_agent);
    }

    /// @notice The owner can always move funds; this is the governance path, not the agent path.
    function ownerTransfer(address to, uint256 amount, bytes32 intentId) external onlyOwner {
        _send(to, amount);
        emit Payment(intentId, to, amount, msg.sender, false);
    }

    function withdrawAll(address to) external onlyOwner {
        uint256 bal = token.balanceOf(address(this));
        _send(to, bal);
        emit Payment(bytes32(0), to, bal, msg.sender, false);
    }

    // ---------------------------------------------------------------- views

    function balance() external view returns (uint256) {
        return token.balanceOf(address(this));
    }

    /// @notice Amount the agent spent in the current hour and the 23 hours before it.
    function spentLast24h() public view returns (uint256 total) {
        uint256 nowHour = block.timestamp / 1 hours;
        for (uint256 i = 0; i < 24; i++) {
            if (bucketHour[i] + 24 > nowHour) total += bucketSpent[i];
        }
    }

    function agentHeadroom() external view returns (uint256) {
        uint256 spent = spentLast24h();
        return spent >= rollingCap ? 0 : rollingCap - spent;
    }

    // ---------------------------------------------------------------- internals

    function _record(uint256 amount) internal {
        uint256 nowHour = block.timestamp / 1 hours;
        uint256 idx = nowHour % 24;
        if (bucketHour[idx] != nowHour) {
            bucketSpent[idx] = 0;
            bucketHour[idx] = nowHour;
        }
        bucketSpent[idx] += amount;
    }

    function _send(address to, uint256 amount) internal {
        if (to == address(0)) revert ZeroAddress();
        if (!token.transfer(to, amount)) revert TransferFailed();
    }
}
