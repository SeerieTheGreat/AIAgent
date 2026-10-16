// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/TestUSDC.sol";
import "../src/PolicyWallet.sol";

contract PolicyWalletTest is Test {
    TestUSDC token;
    PolicyWallet wallet;
    address agent = address(0xA6E7);
    address mama = address(0x1111);
    address stranger = address(0x2222);
    uint256 constant U = 1e6;

    function setUp() public {
        vm.warp(1_800_000_000);
        token = new TestUSDC();
        wallet = new PolicyWallet(agent, address(token), 500 * U, 1000 * U);
        token.mint(address(wallet), 10_000 * U);
        wallet.setAllowlist(mama, true);
    }

    function test_routinePaymentWithinPolicy() public {
        vm.prank(agent);
        wallet.agentTransfer(mama, 20 * U, keccak256("intent-1"));
        assertEq(token.balanceOf(mama), 20 * U);
        assertEq(wallet.spentLast24h(), 20 * U);
        assertEq(wallet.agentHeadroom(), 980 * U);
    }

    function test_eventCarriesIntentId() public {
        bytes32 id = keccak256("intent-2");
        vm.expectEmit(true, true, true, true);
        emit PolicyWallet.Payment(id, mama, 5 * U, agent, false);
        vm.prank(agent);
        wallet.agentTransfer(mama, 5 * U, id);
    }

    function test_revertNotAllowlisted() public {
        vm.prank(agent);
        vm.expectRevert(abi.encodeWithSelector(PolicyWallet.NotAllowlisted.selector, stranger));
        wallet.agentTransfer(stranger, 1 * U, keccak256("x"));
    }

    function test_revertPerTransferCap() public {
        vm.prank(agent);
        vm.expectRevert(abi.encodeWithSelector(PolicyWallet.ExceedsPerTransferCap.selector, 501 * U, 500 * U));
        wallet.agentTransfer(mama, 501 * U, keccak256("x"));
    }

    function test_rollingCapAcrossHours() public {
        vm.startPrank(agent);
        wallet.agentTransfer(mama, 500 * U, keccak256("a"));
        vm.warp(block.timestamp + 3 hours);
        wallet.agentTransfer(mama, 500 * U, keccak256("b"));
        assertEq(wallet.spentLast24h(), 1000 * U);
        vm.expectRevert(abi.encodeWithSelector(PolicyWallet.ExceedsRollingCap.selector, 1 * U, 1000 * U, 1000 * U));
        wallet.agentTransfer(mama, 1 * U, keccak256("c"));
        vm.warp(block.timestamp + 22 hours); // first 500 falls out of the window, second (3h later) still in
        assertEq(wallet.spentLast24h(), 500 * U);
        wallet.agentTransfer(mama, 500 * U, keccak256("d"));
        vm.stopPrank();
        assertEq(token.balanceOf(mama), 1500 * U);
    }

    function test_bucketReuseAfterADay() public {
        vm.startPrank(agent);
        wallet.agentTransfer(mama, 100 * U, keccak256("a"));
        vm.warp(block.timestamp + 24 hours); // same bucket index, new hour -> reset
        assertEq(wallet.spentLast24h(), 0);
        wallet.agentTransfer(mama, 100 * U, keccak256("b"));
        assertEq(wallet.spentLast24h(), 100 * U);
        vm.stopPrank();
    }

    function test_approvalFlow() public {
        bytes32 id = keccak256("request-1");
        wallet.approveOnce(id, stranger, 800 * U);
        vm.prank(agent);
        wallet.agentTransferWithApproval(stranger, 800 * U, id);
        assertEq(token.balanceOf(stranger), 800 * U);
        assertEq(wallet.spentLast24h(), 0); // approved exceptions do not consume the routine cap
        vm.prank(agent);
        vm.expectRevert(PolicyWallet.ApprovalUsed.selector);
        wallet.agentTransferWithApproval(stranger, 800 * U, id);
    }

    function test_approvalMismatchAmountOrRecipient() public {
        bytes32 id = keccak256("request-2");
        wallet.approveOnce(id, stranger, 800 * U);
        vm.startPrank(agent);
        vm.expectRevert(PolicyWallet.ApprovalMismatch.selector);
        wallet.agentTransferWithApproval(stranger, 801 * U, id);
        vm.expectRevert(PolicyWallet.ApprovalMismatch.selector);
        wallet.agentTransferWithApproval(mama, 800 * U, id);
        vm.expectRevert(PolicyWallet.ApprovalMismatch.selector);
        wallet.agentTransferWithApproval(stranger, 800 * U, keccak256("never-approved"));
        vm.stopPrank();
    }

    function test_pauseBlocksAgentPaths() public {
        wallet.setPaused(true);
        bytes32 id = keccak256("request-3");
        wallet.approveOnce(id, stranger, 1 * U);
        vm.startPrank(agent);
        vm.expectRevert(PolicyWallet.IsPaused.selector);
        wallet.agentTransfer(mama, 1 * U, keccak256("x"));
        vm.expectRevert(PolicyWallet.IsPaused.selector);
        wallet.agentTransferWithApproval(stranger, 1 * U, id);
        vm.stopPrank();
    }

    function test_onlyOwnerGovernance() public {
        vm.startPrank(agent);
        vm.expectRevert(PolicyWallet.NotOwner.selector);
        wallet.setPolicy(1, 1);
        vm.expectRevert(PolicyWallet.NotOwner.selector);
        wallet.setAllowlist(stranger, true);
        vm.expectRevert(PolicyWallet.NotOwner.selector);
        wallet.approveOnce(keccak256("r"), stranger, 1);
        vm.expectRevert(PolicyWallet.NotOwner.selector);
        wallet.setPaused(true);
        vm.expectRevert(PolicyWallet.NotOwner.selector);
        wallet.ownerTransfer(stranger, 1, keccak256("r"));
        vm.stopPrank();
    }

    function test_onlyAgentPaths() public {
        vm.expectRevert(PolicyWallet.NotAgent.selector);
        wallet.agentTransfer(mama, 1 * U, keccak256("x"));
    }

    function test_ownerCanAlwaysMoveFunds() public {
        wallet.ownerTransfer(stranger, 2000 * U, keccak256("owner"));
        assertEq(token.balanceOf(stranger), 2000 * U);
        wallet.withdrawAll(address(this));
        assertEq(token.balanceOf(address(wallet)), 0);
    }
}
