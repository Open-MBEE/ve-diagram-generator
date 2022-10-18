
ve_patterns = {
    # for fetching basic artifact info
    'artifactInfo': '''
        (
            artifactName: String, artifactId: java String, artifactURL: String,
            artifactShapeName: String, level: String, identifier: String,
            primaryText: String, maturity: String,
            attributeKey: String, attributeValue: String
        ) {
            Class.name(artifact, artifactName);
            Element.ID(artifact, artifactId);

            find attributeStringValue(artifact, "Source", artifactURL);
            find attributeStringValue(artifact, "Instance Shape", artifactShapeName);
            find attributeStringValue(artifact, "Level", level);
            find attributeStringValue(artifact, "Identifier", identifier);
            
            find attributeStringValue(artifact, "Primary Text", primaryText);
            find attributeStringValue(artifact, "Maturity", maturity);

            find attributeStringArray(artifact, attributeKey, attributeValue);
        }
    ''',

    # for fetching children
    'artifactChildren': '''
        (
            artifactId: java String,
            child, childName: String
        ) {
            Element.ID(artifact, artifactId);

            Class.ownedAttribute(child, childProperty);
            Property.name(childProperty, "Child Of");
            Property.type(childProperty, artifact);
            
            Class.name(child, childName);
            find attributeStringValue(child, "Source", childURL);
        }
    ''',

    # for fetching string arrays
    'artifactAttributeStringArray': '''
        (
            artifactId: java String,
            attributeKey: String, itemValue: String
        ) {
            Element.ID(artifact, artifactId);

            find attributeStringArray(artifact, attributeKey, itemValue);
        }
    '''
}
