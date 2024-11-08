window.app.component('relay-details', {
  name: 'relay-details',
  template: '#relay-details',
  props: ['relay-id', 'adminkey', 'inkey', 'wallet-options'],
  data() {
    return {
      tab: 'info',
      relay: null,
      accounts: [],
      accountPubkey: '',
      formDialogItem: {
        show: false,
        data: {
          name: '',
          description: ''
        }
      },
      showBlockedAccounts: true,
      showAllowedAccounts: false,
      accountsTable: {
        columns: [
          {
            name: 'action',
            align: 'left',
            label: '',
            field: ''
          },
          {
            name: 'pubkey',
            align: 'left',
            label: 'Public Key',
            field: 'pubkey'
          },
          {
            name: 'allowed',
            align: 'left',
            label: 'Allowed',
            field: 'allowed'
          },
          {
            name: 'blocked',
            align: 'left',
            label: 'Blocked',
            field: 'blocked'
          },
          {
            name: 'paid_to_join',
            align: 'left',
            label: 'Paid to join',
            field: 'paid_to_join'
          },
          {
            name: 'sats',
            align: 'left',
            label: 'Spent Sats',
            field: 'sats'
          },
          {
            name: 'storage',
            align: 'left',
            label: 'Storage',
            field: 'storage'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      skipEventKind: 0,
      forceEventKind: 0
    }
  },

  computed: {
    hours() {
      const y = []
      for (let i = 0; i <= 24; i++) {
        y.push(i)
      }
      return y
    },
    range60() {
      const y = []
      for (let i = 0; i <= 60; i++) {
        y.push(i)
      }
      return y
    },
    storageUnits() {
      return ['KB', 'MB']
    },
    fullStorageActions() {
      return [
        {value: 'block', label: 'Block New Events'},
        {value: 'prune', label: 'Prune Old Events'}
      ]
    },
    wssLink() {
      this.relay.meta.domain =
        this.relay.meta.domain || window.location.hostname
      return 'wss://' + this.relay.meta.domain + '/nostrrelay/' + this.relay.id
    }
  },

  methods: {
    satBtc(val, showUnit = true) {
      return satOrBtc(val, showUnit, this.satsDenominated)
    },
    deleteRelay() {
      LNbits.utils
        .confirmDialog(
          'All data will be lost! Are you sure you want to delete this relay?'
        )
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              '/nostrrelay/api/v1/relay/' + this.relayId,
              this.adminkey
            )
            this.$emit('relay-deleted', this.relayId)
            Quasar.Notify.create({
              type: 'positive',
              message: 'Relay Deleted',
              timeout: 5000
            })
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async getRelay() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/nostrrelay/api/v1/relay/' + this.relayId,
          this.inkey
        )
        this.relay = data
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async updateRelay() {
      try {
        const {data} = await LNbits.api.request(
          'PATCH',
          '/nostrrelay/api/v1/relay/' + this.relayId,
          this.adminkey,
          this.relay
        )
        this.relay = data
        this.$emit('relay-updated', this.relay)
        this.$q.notify({
          type: 'positive',
          message: 'Relay Updated',
          timeout: 5000
        })
      } catch (error) {
        console.warn(error)
        LNbits.utils.notifyApiError(error)
      }
    },
    togglePaidRelay: async function () {
      this.relay.meta.wallet =
        this.relay.meta.wallet || this.walletOptions[0].value
    },
    getAccounts: async function () {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/nostrrelay/api/v1/account?relay_id=${this.relay.id}&allowed=${this.showAllowedAccounts}&blocked=${this.showBlockedAccounts}`,
          this.inkey
        )
        this.accounts = data
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    allowPublicKey: async function (pubkey, allowed) {
      await this.updatePublicKey({pubkey, allowed})
    },
    blockPublicKey: async function (pubkey, blocked = true) {
      await this.updatePublicKey({pubkey, blocked})
    },
    removePublicKey: async function (pubkey) {
      LNbits.utils
        .confirmDialog('This public key will be removed from relay!')
        .onOk(async () => {
          await this.deletePublicKey(pubkey)
        })
    },
    togglePublicKey: async function (account, action) {
      if (action === 'allow') {
        await this.updatePublicKey({
          pubkey: account.pubkey,
          allowed: account.allowed
        })
      }
      if (action === 'block') {
        await this.updatePublicKey({
          pubkey: account.pubkey,
          blocked: account.blocked
        })
      }
    },
    updatePublicKey: async function (ops) {
      try {
        await LNbits.api.request(
          'PUT',
          '/nostrrelay/api/v1/account',
          this.adminkey,
          {
            relay_id: this.relay.id,
            pubkey: ops.pubkey,
            allowed: ops.allowed,
            blocked: ops.blocked
          }
        )
        this.$q.notify({
          type: 'positive',
          message: 'Account Updated',
          timeout: 5000
        })
        this.accountPubkey = ''
        await this.getAccounts()
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    deletePublicKey: async function (pubkey) {
      try {
        await LNbits.api.request(
          'DELETE',
          `/nostrrelay/api/v1/account/${this.relay.id}/${pubkey}`,
          this.adminkey,
          {}
        )
        this.$q.notify({
          type: 'positive',
          message: 'Account Deleted',
          timeout: 5000
        })
        await this.getAccounts()
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    addSkipAuthForEvent: function () {
      value = +this.skipEventKind
      if (this.relay.meta.skipedAuthEvents.indexOf(value) != -1) {
        return
      }
      this.relay.meta.skipedAuthEvents.push(value)
    },
    removeSkipAuthForEvent: function (eventKind) {
      value = +eventKind
      this.relay.meta.skipedAuthEvents =
        this.relay.meta.skipedAuthEvents.filter(e => e !== value)
    },
    addForceAuthForEvent: function () {
      value = +this.forceEventKind
      if (this.relay.meta.forcedAuthEvents.indexOf(value) != -1) {
        return
      }
      this.relay.meta.forcedAuthEvents.push(value)
    },
    removeForceAuthForEvent: function (eventKind) {
      value = +eventKind
      this.relay.meta.forcedAuthEvents =
        this.relay.meta.forcedAuthEvents.filter(e => e !== value)
    },
    // todo: bad. base.js not present in custom components
    copyText: function (text, message, position) {
      Quasar.copyToClipboard(text).then(function () {
        Quasar.Notify.create({
          message: message || 'Copied to clipboard!',
          position: position || 'bottom'
        })
      })
    }
  },

  async created() {
    await this.getRelay()
    await this.getAccounts()
  }
})
