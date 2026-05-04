using SampleSolution.Core.Services;

namespace SampleSolution.Api;

public class AppSetup
{
    private readonly IContainer _container;

    public AppSetup(IContainer container)
    {
        _container = container;
    }

    public void RegisterServices()
    {
        _container.RegisterType<IUserService, UserService>();
        _container.RegisterSingleton<IUserRepository, UserRepository>();
    }
}

public interface IContainer
{
    void RegisterType<TInterface, TImpl>();
    void RegisterSingleton<TInterface, TImpl>();
}
