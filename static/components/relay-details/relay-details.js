async function relayDetails(path) {
  const template = await loadTemplateAsync(path)
  Vue.component('relay-details', {
    name: 'relay-details',
    template,

    props: ['relay-id', 'adminkey', 'inkey', 'wallet-options'],
    data: function () {
      return {
        tab: 'info',
        relay: null,
        blockedPubkey: '',
        allowedPubkey: '',
        formDialogItem: {
          show: false,
          data: {
            name: '',
            description: ''
          }
        },
        skipEventKind: 0,
        forceEventKind: 0
      }
    },

    computed: {
      hours: function () {
        const y = []
        for (let i = 0; i <= 24; i++) {
          y.push(i)
        }
        return y
      },
      range60: function () {
        const y = []
        for (let i = 0; i <= 60; i++) {
          y.push(i)
        }
        return y
      },
      storageUnits: function () {
        return ['KB', 'MB']
      },
      fullStorageActions: function () {
        return [
          {value: 'block', label: 'Block New Events'},
          {value: 'prune', label: 'Prune Old Events'}
        ]
      }
    },

    methods: {
      satBtc(val, showUnit = true) {
        return satOrBtc(val, showUnit, this.satsDenominated)
      },
      deleteRelay: function () {
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
              this.$q.notify({
                type: 'positive',
                message: 'Relay Deleted',
                timeout: 5000
              })
            } catch (error) {
              console.warn(error)
              LNbits.utils.notifyApiError(error)
            }
          })
      },
      getRelay: async function () {
        try {
          const {data} = await LNbits.api.request(
            'GET',
            '/nostrrelay/api/v1/relay/' + this.relayId,
            this.inkey
          )
          this.relay = data

          console.log('###  this.relay', this.relay)
        } catch (error) {
          LNbits.utils.notifyApiError(error)
        }
      },
      updateRelay: async function () {
        try {
          const {data} = await LNbits.api.request(
            'PUT',
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
          LNbits.utils.notifyApiError(error)
        }
      },
      togglePaidRelay: async function () {
        this.relay.config.wallet =
          this.relay.config.wallet || this.walletOptions[0].value
      },
      allowPublicKey: function () {
        this.relay.config.allowedPublicKeys.push(this.allowedPubkey)
        this.allowedPubkey = ''
      },
      blockPublicKey: function () {
        this.relay.config.blockedPublicKeys.push(this.blockedPubkey)
        this.blockedPubkey = ''
      },
      deleteAllowedPublicKey: function (pubKey) {
        this.relay.config.allowedPublicKeys =
          this.relay.config.allowedPublicKeys.filter(p => p !== pubKey)
      },

      deleteBlockedPublicKey: function (pubKey) {
        this.relay.config.blockedPublicKeys =
          this.relay.config.blockedPublicKeys.filter(p => p !== pubKey)
      },
      addSkipAuthForEvent: function () {
        value = +this.skipEventKind
        if (this.relay.config.skipedAuthEvents.indexOf(value) != -1) {
          return
        }
        this.relay.config.skipedAuthEvents.push(value)
      },
      removeSkipAuthForEvent: function (eventKind) {
        value = +eventKind
        this.relay.config.skipedAuthEvents =
          this.relay.config.skipedAuthEvents.filter(e => e !== value)
      },
      addForceAuthForEvent: function () {
        value = +this.forceEventKind
        if (this.relay.config.forcedAuthEvents.indexOf(value) != -1) {
          return
        }
        this.relay.config.forcedAuthEvents.push(value)
      },
      removeSkipAuthForEvent: function (eventKind) {
        value = +eventKind
        this.relay.config.forcedAuthEvents =
          this.relay.config.forcedAuthEvents.filter(e => e !== value)
      }
    },

    created: async function () {
      await this.getRelay()
    }
  })
}
