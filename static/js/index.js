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
          showAdvanced: false,
          data: {
            name: '',
            description: '',
            type: '',
            amount: '',
            wallet: ''
          }
        },
        relayTypes: [
          {
            id: 'rating',
            label: 'Rating (rate one item from a list)'
          },
          {
            id: 'poll',
            label: 'Poll (choose one item from a list)'
          },
          {
            id: 'likes',
            label: 'Likes (like or dislike an item)'
          }
        ],

        relaysTable: {
          columns: [
            {
              name: '',
              align: 'left',
              label: '',
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
              name: 'type',
              align: 'left',
              label: 'Type',
              field: 'type'
            },
            {
              name: 'amount',
              align: 'left',
              label: 'Amount',
              field: 'amount'
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
          name: '',
          description: '',
          type: this.relayTypes[0],
          amount: '100',
          wallet: ''
        }
      },
      getRelayTypeLabel: function (relayType) {
        const type = this.relayTypes.find(s => (s.id = relayType))
        return type ? type.label : '?'
      },
      openCreateRelayDialog: function () {
        this.formDialogRelay.data = this.getDefaultRelayData()
        this.formDialogRelay.show = true
      },
      getRelays: async function () {
        try {
          const {data} = await LNbits.api.request(
            'GET',
            '/reviews/api/v1/survey',
            this.g.user.wallets[0].inkey
          )
          this.relayLinks = data.map(c =>
            mapRelay(
              c,
              this.relayLinks.find(old => old.id === c.id)
            )
          )
          console.log('### relayLinks', this.relayLinks)
        } catch (error) {
          console.log('### getRelays', error)
          LNbits.utils.notifyApiError(error)
        }
      },

      createRelay: async function (data) {
        try {
          data.type = data.type.id
          const resp = await LNbits.api.request(
            'POST',
            '/reviews/api/v1/survey',
            this.g.user.wallets[0].adminkey,
            data
          )

          this.relayLinks.unshift(mapRelay(resp.data))
          this.formDialogRelay.show = false
        } catch (error) {
          LNbits.utils.notifyApiError(error)
        }
      },

      deleteRelay: function (relayId) {
        LNbits.utils
          .confirmDialog('Are you sure you want to delete this survet?')
          .onOk(async () => {
            try {
              const response = await LNbits.api.request(
                'DELETE',
                '/reviews/api/v1/survey/' + relayId,
                this.g.user.wallets[0].adminkey
              )

              this.relayLinks = _.reject(this.relayLinks, function (obj) {
                return obj.id === relayId
              })
            } catch (error) {
              LNbits.utils.notifyApiError(error)
            }
          })
      },

      sendFormDataRelay: async function () {
        console.log('### sendFormDataRelay')
        this.createRelay(this.formDialogRelay.data)
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
