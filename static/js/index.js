const relays = async () => {
  Vue.component(VueQrcode.name, VueQrcode)

  await relayDetails('static/components/relay-details/relay-details.html')

  new Vue({
    el: '#vue',
    mixins: [windowMixin],
    data: function () {
      return {
        filter: '',
        relayLinks: [],
        formDialogRelay: {
          show: false,
          data: {
            id: '',
            name: '',
            description: '',
            pubkey: '',
            contact: ''
          }
        },

        relaysTable: {
          columns: [
            {
              name: '',
              align: 'left',
              label: '',
              field: ''
            },
            {
              name: 'id',
              align: 'left',
              label: 'ID',
              field: 'id'
            },
            {
              name: 'toggle',
              align: 'left',
              label: 'Active',
              field: ''
            },
            {
              name: 'name',
              align: 'left',
              label: 'Name',
              field: 'name'
            },
            {
              name: 'description',
              align: 'left',
              label: 'Description',
              field: 'description'
            },
            {
              name: 'pubkey',
              align: 'left',
              label: 'Public Key',
              field: 'pubkey'
            },
            {
              name: 'contact',
              align: 'left',
              label: 'Contact',
              field: 'contact'
            }
          ],
          pagination: {
            rowsPerPage: 10
          }
        }
      }
    },
    methods: {
      getDefaultRelayData: function () {
        return {
          id: '',
          name: '',
          description: '',
          pubkey: '',
          contact: ''
        }
      },

      openCreateRelayDialog: function () {
        this.formDialogRelay.data = this.getDefaultRelayData()
        this.formDialogRelay.show = true
      },
      getRelays: async function () {
        try {
          const {data} = await LNbits.api.request(
            'GET',
            '/nostrrelay/api/v1/relay',
            this.g.user.wallets[0].inkey
          )
          this.relayLinks = data.map(c =>
            mapRelay(
              c,
              this.relayLinks.find(old => old.id === c.id)
            )
          )
        } catch (error) {
          LNbits.utils.notifyApiError(error)
        }
      },

      createRelay: async function (data) {
        try {
          const resp = await LNbits.api.request(
            'POST',
            '/nostrrelay/api/v1/relay',
            this.g.user.wallets[0].adminkey,
            data
          )

          this.relayLinks.unshift(mapRelay(resp.data))
          this.formDialogRelay.show = false
        } catch (error) {
          LNbits.utils.notifyApiError(error)
        }
      },
      showToggleRelayDialog: function (relay) {
        if (relay.active) {
          this.toggleRelay(relay)
          return
        }
        LNbits.utils
          .confirmDialog('Are you sure you want to deactivate this relay?')
          .onOk(async () => {
            this.toggleRelay(relay)
          })
          .onCancel(async () => {
            relay.active = !relay.active
          })
      },
      toggleRelay: async function (relay) {
        try {
          await LNbits.api.request(
            'PUT',
            '/nostrrelay/api/v1/relay/' + relay.id,
            this.g.user.wallets[0].adminkey,
            {}
          )
        } catch (error) {
          LNbits.utils.notifyApiError(error)
        }
      },

      sendFormDataRelay: async function () {
        this.createRelay(this.formDialogRelay.data)
      },

      handleRelayDeleted: function (relayId) {
        this.relayLinks = _.reject(this.relayLinks, function (obj) {
          return obj.id === relayId
        })
      },
      handleRelayUpdated: function (relay) {
        const index = this.relayLinks.findIndex(r => r.id === relay.id)
        if (index !== -1) {
          relay.expanded = true
          this.relayLinks.splice(index, 1, relay)
        }
      },

      exportrelayCSV: function () {
        LNbits.utils.exportCSV(
          this.relaysTable.columns,
          this.relayLinks,
          'relays'
        )
      }
    },
    created: async function () {
      await this.getRelays()
    }
  })
}

relays()
