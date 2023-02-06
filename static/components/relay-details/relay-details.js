async function relayDetails(path) {
  const template = await loadTemplateAsync(path)
  Vue.component('relay-details', {
    name: 'relay-details',
    template,

    props: [],
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
    },

    created: async function () {
      
    }
  })
}
