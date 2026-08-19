# Guardian Family Identity

This context defines who belongs to a family and which protected people and devices that family owns.

## Language

**Account**:
A global adult identity that can belong to more than one Family. It is never a Child.
_Avoid_: Parent, user, guardian account

**Family**:
The mandatory tenant and privacy boundary for all protected-person, device, policy, incident, evidence, command, and report data.
_Avoid_: Household, workspace, account

**Membership**:
The relationship that grants an Account a role in one Family. A revoked Membership grants no access.
_Avoid_: Family user, permission

**Owner**:
An active Membership role responsible for Family administration. A Family always retains at least one active Owner.
_Avoid_: Admin

**Guardian**:
An active Membership role that can use protection workflows but cannot remove the final Owner.
_Avoid_: Parent

**Child**:
A protected person owned by exactly one Family and deliberately not modeled as an Account.
_Avoid_: Minor account, user

**Device**:
A protected endpoint owned by exactly one Family and assigned to exactly one Child in that same Family.
_Avoid_: Agent, computer

**Device Lifecycle Status**:
Whether a Device identity is active or revoked. It is independent from Protection Status.
_Avoid_: Protection state

**Protection Status**:
A derived statement about recent heartbeat and protection health; registration alone never makes a Device protected.
_Avoid_: Device status

**Family Scope**:
The authenticated, active Membership capability for exactly one Family. Resource identifiers never create or expand it.
_Avoid_: Tenant ID, family query parameter

**Demo Mode**:
An explicit local-only mode containing deterministic synthetic identities. It is forbidden in staging and production.
_Avoid_: Default data, fallback tenant
