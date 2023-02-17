# Nostr Relay

## One click and spin up your own Nostr relay. Share with the world, or use privately.


### Usage
Install this extension into your LNbits instance.
....


## Supported NIPs
 - [x] **NIP-01**: Basic protocol flow
 - [x] **NIP-02**: Contact List and Petnames
   - `kind: 3`: delete past contact lists as soon as the relay receives a new one
 - [x] **NIP-04**: Encrypted Direct Message
   - if `AUTH` enabled: send only to the intended target
 - [x] **NIP-09**: Event Deletion
 - [x] **NIP-11**: Relay Information Document
   - >**Note**: the endpoint is NOT on the root level of the domain. It also includes a path (eg https://lnbits.link/nostrrelay/)
 - [ ] **NIP-12**: Generic Tag Queries
   - todo
 - [x] **NIP-15**: End of Stored Events Notice
 - [x] **NIP-16**: Event Treatment
   - [x] Regular Events
   - [x] Replaceable Events
   - [x] Ephemeral Events
 - [x] **NIP-20**: Command Results
   - todo: use correct prefixes
 - [x] **NIP-22**: Event created_at Limits
 - [ ] **NIP-26**: Delegated Event Signing
   - not planned
 - [x] **NIP-28** Public Chat
   - `kind: 41`: handled similar to `kind 0` metadata events
 - [ ] **NIP-33**: Parameterized Replaceable Events
   - todo
 - [ ] **NIP-40**: Expiration Timestamp
   - todo
 - [x] **NIP-42**: Authentication of clients to relays
   - todo: use correct prefix
 - [ ] **NIP-50**: Search Capability
   - todo

## Usage
### Create Relay
Creating a new relay is straightforward. Just click `New Relay` then enter the Relay Info.
> *Note*: admin users can select a relay id. Regular users will be assigned a generated relay id.
The relay can be activated/deactivated.

![image](https://user-images.githubusercontent.com/2951406/219601417-9292d5b9-d96c-4ff6-a6fd-6c8b37b9872d.png)

### Configure Relay


## Development

Create Symbolic Link:
```
ln -s /Users/my-user/git-repos/nostr-relay-extension/ /Users/my-user/git-repos/lnbits/lnbits/extensions/nostrrelay
```
