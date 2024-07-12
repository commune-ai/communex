import re
from typing import Any, cast

import typer
from typer import Context

from communex.balance import from_nano
from communex.cli._common import (make_custom_context,
                                  print_table_from_plain_dict, print_table_standardize)
from communex.compat.key import resolve_key_ss58, try_classic_load_key
from communex.errors import ChainTransactionError
from communex.misc import IPFS_REGEX, get_map_subnets_params
from communex.types import SubnetParams

subnet_app = typer.Typer(no_args_is_help=True)


@subnet_app.command()
def list(ctx: Context):
    """
    Gets subnets.
    """
    context = make_custom_context(ctx)
    client = context.com_client()

    with context.progress_status("Getting subnets ..."):
        subnets = get_map_subnets_params(client)

    keys, values = subnets.keys(), subnets.values()
    subnets_with_netuids = [
        {"netuid": key, **value} for key, value in zip(keys, values)
    ]

    for subnet_dict in subnets_with_netuids:  # type: ignore
        bonds = subnet_dict["bonds_ma"]  # type: ignore
        if bonds:
            subnet_dict["bonds_ma"] = str(
                from_nano(subnet_dict["bonds_ma"])) + " J"  # type: ignore

    for dict in subnets_with_netuids:  # type: ignore
        print_table_from_plain_dict(
            dict, ["Params", "Values"], context.console)  # type: ignore


@subnet_app.command()
def distribution(ctx: Context):
    context = make_custom_context(ctx)
    client = context.com_client()

    with context.progress_status("Getting emission distribution..."):
        subnets_emission = client.query_map_subnet_emission()
        subnet_consensus = client.query_map_subnet_consensus()
        subnet_names = client.query_map_subnet_names()
        total_emission = sum(subnets_emission.values())
        subnet_emission_percentages = {
            key: value / total_emission * 100 for key, value in subnets_emission.items()
        }

    # Prepare the data for the table
    table_data: dict[str, Any] = {
        "Subnet": [],
        "Name": [],
        "Consensus": [],
        "Emission %": []
    }

    for subnet, emission_percentage in subnet_emission_percentages.items():
        if emission_percentage > 0:
            table_data["Subnet"].append(str(subnet))
            table_data["Name"].append(subnet_names.get(subnet, "N/A"))
            table_data["Consensus"].append(subnet_consensus.get(subnet, "N/A"))
            table_data["Emission %"].append(f"{round(emission_percentage, 2)}%")

    print_table_standardize(table_data, context.console)


@subnet_app.command()
def legit_whitelist(ctx: Context):
    """
    Gets the legitimate whitelist of modules for the general subnet 0
    """

    context = make_custom_context(ctx)
    client = context.com_client()

    with context.progress_status("Getting legitimate whitelist ..."):
        whitelist = cast(dict[str, int], client.query_map_legit_whitelist())

    print_table_from_plain_dict(
        whitelist, ["Module", "Recommended weight"], context.console
    )


@subnet_app.command()
def info(ctx: Context, netuid: int):
    """
    Gets subnet info.
    """
    context = make_custom_context(ctx)
    client = context.com_client()

    with context.progress_status(f"Getting subnet with netuid '{netuid}'..."):

        subnets = get_map_subnets_params(client)
        subnet = subnets.get(netuid, None)

    if subnet is None:
        raise ValueError("Subnet not found")

    general_subnet: dict[str, Any] = cast(dict[str, Any], subnet)
    print_table_from_plain_dict(
        general_subnet, ["Params", "Values"], context.console)


# TODO refactor (user does not need to specify all params)
@subnet_app.command()
def update(
    ctx: Context,
    netuid: int,
    key: str,
    founder: str = typer.Option(None),
    founder_share: int = typer.Option(None),
    immunity_period: int = typer.Option(None),
    incentive_ratio: int = typer.Option(None),
    max_allowed_uids: int = typer.Option(None),
    max_allowed_weights: int = typer.Option(None),
    min_allowed_weights: int = typer.Option(None),
    max_weight_age: int = typer.Option(None),
    min_stake: int = typer.Option(None),
    name: str = typer.Option(None),
    tempo: int = typer.Option(None),
    trust_ratio: int = typer.Option(None),
    bonds_ma: int = typer.Option(None),
    maximum_set_weight_calls_per_epoch: int = typer.Option(None),
    target_registrations_per_interval: int = typer.Option(None),
    target_registrations_interval: int = typer.Option(None),
    max_registrations_per_interval: int = typer.Option(None),
    vote_mode: str = typer.Option(None),
    adjustment_alpha: int = typer.Option(None),
    min_immunity_stake: int = typer.Option(None),
):
    """
    Updates a subnet.
    """
    provided_params = locals().copy()
    provided_params.pop("ctx")
    provided_params.pop("key")
    provided_params.pop("netuid")
    provided_params = {
        key: value for key, value in provided_params.items() if value is not None
    }

    context = make_custom_context(ctx)
    client = context.com_client()
    subnets_info = get_map_subnets_params(client)
    subnet_params = subnets_info[netuid]
    subnet_params = dict(subnet_params)
    subnet_params.pop("emission")
    subnet_params = cast(SubnetParams, subnet_params)
    provided_params = cast(SubnetParams, provided_params)
    subnet_params.update(provided_params)
    # because bonds_ma and maximum_set_weights dont have a default value
    if subnet_params.get("bonds_ma", None) is None:
        subnet_params["bonds_ma"] = client.query("BondsMovingAverage")
    if subnet_params.get("maximum_set_weight_calls_per_epoch", None) is None:
        subnet_params["maximum_set_weight_calls_per_epoch"] = client.query(
            "MaximumSetWeightCallsPerEpoch"
        )
    resolved_key = try_classic_load_key(key)
    with context.progress_status("Updating subnet ..."):
        response = client.update_subnet(
            key=resolved_key, params=subnet_params, netuid=netuid
        )

    if response.is_success:
        context.info(
            f"Successfully updated subnet {subnet_params['name']} with netuid {netuid}"
        )
    else:
        raise ChainTransactionError(response.error_message)  # type: ignore


@subnet_app.command()
def propose_on_subnet(
    ctx: Context,
    netuid: int,
    key: str,
    cid: str,
    founder: str = typer.Option(None),
    founder_share: int = typer.Option(None),
    immunity_period: int = typer.Option(None),
    incentive_ratio: int = typer.Option(None),
    max_allowed_uids: int = typer.Option(None),
    max_allowed_weights: int = typer.Option(None),
    min_allowed_weights: int = typer.Option(None),
    max_weight_age: int = typer.Option(None),
    min_stake: int = typer.Option(None),
    name: str = typer.Option(None),
    tempo: int = typer.Option(None),
    trust_ratio: int = typer.Option(None),
    bonds_ma: int = typer.Option(None),
    maximum_set_weight_calls_per_epoch: int = typer.Option(None),
    target_registrations_per_interval: int = typer.Option(None),
    target_registrations_interval: int = typer.Option(None),
    max_registrations_per_interval: int = typer.Option(None),
    vote_mode: str = typer.Option(None),
    adjustment_alpha: int = typer.Option(None),
    min_immunity_stake: int = typer.Option(None),
):
    """
    Adds a proposal to a specific subnet.
    """
    context = make_custom_context(ctx)
    if not re.match(IPFS_REGEX, cid):
        context.error(f"CID provided is invalid: {cid}")
        exit(1)
    else:
        ipfs_prefix = "ipfs://"
        cid = ipfs_prefix + cid

    provided_params = locals().copy()
    provided_params.pop("ctx")
    provided_params.pop("context")
    provided_params.pop("key")
    provided_params.pop("netuid")
    provided_params.pop("ipfs_prefix")
    if provided_params["founder"] is not None:
        resolve_founder = resolve_key_ss58(founder)
        provided_params["founder"] = resolve_founder
    provided_params = {
        key: value for key, value in provided_params.items() if value is not None
    }

    client = context.com_client()
    subnets_info = get_map_subnets_params(client)
    subnet_params = subnets_info[netuid]
    subnet_params = dict(subnet_params)
    subnet_params.pop("emission")
    subnet_params = cast(SubnetParams, subnet_params)
    provided_params = cast(SubnetParams, provided_params)
    subnet_params.update(provided_params)
    # because bonds_ma and maximum_set_weights dont have a default value
    if subnet_params.get("bonds_ma", None) is None:
        subnet_params["bonds_ma"] = client.query("BondsMovingAverage")
    if subnet_params.get("maximum_set_weight_calls_per_epoch", None) is None:
        subnet_params["maximum_set_weight_calls_per_epoch"] = client.query(
            "MaximumSetWeightCallsPerEpoch"
        )

    resolved_key = try_classic_load_key(key)

    with context.progress_status("Adding a proposal..."):
        client.add_subnet_proposal(
            resolved_key,
            subnet_params,
            cid,
            netuid=netuid
        )


@subnet_app.command()
def submit_general_subnet_application(
    ctx: Context, key: str, application_key: str, cid: str
):
    """
    Submits a legitimate whitelist application to the general subnet, netuid 0.
    """

    context = make_custom_context(ctx)
    if not re.match(IPFS_REGEX, cid):
        context.error(f"CID provided is invalid: {cid}")
        exit(1)

    client = context.com_client()

    resolved_key = try_classic_load_key(key)
    resolved_application_key = resolve_key_ss58(application_key)

    # append the ipfs hash
    ipfs_prefix = "ipfs://"
    cid = ipfs_prefix + cid

    with context.progress_status("Adding a application..."):
        client.add_dao_application(resolved_key, resolved_application_key, cid)


@subnet_app.command()
def add_custom_proposal(
    ctx: Context,
    key: str,
    cid: str,
    netuid: int,
):
    """
    Adds a custom proposal to a specific subnet.
    """

    context = make_custom_context(ctx)
    if not re.match(IPFS_REGEX, cid):
        context.error(f"CID provided is invalid: {cid}")
        exit(1)

    client = context.com_client()

    resolved_key = try_classic_load_key(key)

    # append the ipfs hash
    ipfs_prefix = "ipfs://"
    cid = ipfs_prefix + cid

    with context.progress_status("Adding a proposal..."):
        client.add_custom_subnet_proposal(resolved_key, cid, netuid=netuid)


@subnet_app.command()
def list_curator_applications(
    ctx: Context
):
    """
    Lists all curator applications.
    """
    context = make_custom_context(ctx)
    client = context.com_client()

    with context.progress_status("Querying applications..."):
        apps = client.query_map_curator_applications()
    print(apps)
