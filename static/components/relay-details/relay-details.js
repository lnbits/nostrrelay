async function relayDetails(path) {
  const template = await loadTemplateAsync(path)
  Vue.component('relay-details', {
    name: 'relay-details',
    template,

    props: ['relay-id', 'adminkey', 'inkey'],
    data: function () {
      return {
        items: [],
        formDialogItem: {
          show: false,
          data: {
            name: '',
            description: ''
          }
        }
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
            } catch (error) {
              console.warn(error)
              LNbits.utils.notifyApiError(error)
            }
          })
      }
    },

    created: async function () {}
  })
}
