navigator_hardwareConcurrency = """
const patchNavigator = (name, value) =>
    window.utils.replaceProperty(Object.getPrototypeOf(navigator), name, {
        get() {
            return value
        }
    })

patchNavigator('hardwareConcurrency', window.opts.navigator_hardware_concurrency || 4);
"""
