"""Configurable, conservative audience and aggression checks for sayings."""
import unicodedata


def normalized(text):
    return unicodedata.normalize('NFKC', text).casefold()


def audience(*metadata):
    """Use explicit transport metadata only, never infer ownership from text."""
    levels = []
    for item in metadata:
        if not isinstance(item, dict):
            continue
        for key in ('audience', 'chatType', 'chat_type'):
            if key in item:
                value = item[key]
                levels.append('owner' if value in ('owner', 'private', 'direct') else
                              'group' if value == 'group' else 'third_party' if value == 'third_party' else 'unknown')
        if item.get('isGroup') is True or item.get('groupId'):
            levels.append('group')
    return next((v for v in levels if v != 'owner'), levels[0] if levels else None)


def expression_allowed(value, policy, user=''):
    if value['source'].get('audience', 'owner') != 'owner':
        return False
    text = normalized(value['expression'] or '')
    context = normalized(user) + '\n' + text
    return (not any(normalized(w) in context for w in policy.get('non_owner_markers', []))
            and not any(normalized(w) in text for w in policy.get('aggressive_keywords', [])))
