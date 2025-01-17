navigator_languages = """
Object.defineProperty(Object.getPrototypeOf(navigator), 'languages', {
    get: () => window.opts.languages || ['en-US', 'en']
})

"""
